# 提示词-模型绑定关系重构 - Product Requirement Document

## Overview
- **Summary**: 重构系统提示词与 AI 模型的绑定关系，从"多条 prompt 可绑同一模型 + is_default 选一条生效"改为"一对一硬绑定 + 应用层校验"，同时支持前端通过 `prompt_code` 传参在每次对话中附加一条"自由漂浮"的可选提示词。最终 system prompt 拼接顺序固定为：身份声明 → 全局默认 → 模型绑定 prompt → 前端指定可选 prompt → 用户自定义 system。
- **Purpose**: 消除当前多对一绑定导致的隐式覆盖行为（后加载的 prompt 赢），统一全局默认的判断逻辑，并赋予前端按次对话选择提示词的能力。
- **Target Users**: 后端开发者（维护 prompt 管理接口）、前端开发者（调用 AI 对话接口）、产品/运营（通过后台配置系统提示词）。

## Goals
- 一条 AI 模型最多被一条 prompt 绑定；创建/更新 prompt 时如果指定了 `model_code`，需要应用层校验该模型是否已被占用
- 统一全局默认 prompt 的判断逻辑（消除 `prompt_code=="Global_Default_Prompt"` 和 `model_code is null AND is_default=True` 两套并存的不一致）
- AI 对话接口（`/chat` 和 `/chat/chat/stream`）新增可选参数 `prompt_code`，支持前端指定一条"自由漂浮"的提示词追加到 system prompt 末尾
- 前端指定的 prompt_code 必须满足：非绑定（`model_code is None`）且非全局默认（`is_default=False`）；不满足时返回明确错误
- 拼接过程中去重：如果前端指定 prompt 的 content 与已拼接的任何一段完全相同，则跳过不重复追加
- 保持现有 `is_default` 字段的语义不变（全局默认 prompt 仍靠 `is_default=True AND model_code is None` 识别）

## Non-Goals (Out of Scope)
- 不修改 DB 表结构（不加 unique constraint；应用层校验即可）
- 不删除现有 prompt 管理接口（只增强 create/update 的校验逻辑）
- 不改变 AI Provider 层的调用方式（prompt 拼接仍在 dispatcher 层完成）
- 不实现前端 UI 改造（后端只提供能力）
- 不处理历史脏数据（当前 DB 里如果已有多条 prompt 绑了同一 model_code，由运维手动清理后再部署；或后续 migration 处理）
- 不修改 `is_default` 字段本身的定义

## Background & Context

### 当前拼接逻辑
```
_build_identity_system(config, user_system):
  [1] 身份声明硬编码注入
  [2] global_default = prompt_cache.global_default  ← prompt_code=="Global_Default_Prompt" 硬编码匹配
  [3] db_prompt = prompt_cache.resolve(model_code)  ← _model_defaults[model_code]，is_default=True 的那条；多条同 model_code 时后加载覆盖
  [4] user_system 追加
```

### 当前 PromptCache 两套判断逻辑的不一致
| 位置 | 全局默认判断 | 模型绑定判断 |
|---|---|---|
| `prompt_cache.warm_up()` | `prompt_code == "Global_Default_Prompt"`（硬编码字符串） | `is_default=True AND model_code 非空` |
| `prompt_repository.get_global_default()` | `model_code is null AND is_default=True` | — |

这意味着 DB 里设了 `model_code=null AND is_default=True` 的记录，cache **不会**把它识别为全局默认，因为 cache 只认那个硬编码的 prompt_code。

### 当前多对一绑定的隐式覆盖
`_model_defaults` 是一个 `dict[str, SystemPrompt]`，warm_up 遍历 DB 记录时后加载的同 model_code 会静默覆盖前者，没有任何警告或约束。

## Functional Requirements

- **FR-1**: 当创建 prompt 时前端传了 `model_code`（非空非 None），后端需要校验当前 DB 中是否存在**另一条未删除**的 prompt 已绑定该 model_code；存在则返回 400 错误。
- **FR-2**: 当更新 prompt 时如果要修改 `model_code` 字段，需要同样校验目标 model_code 是否已被其他 prompt 占用。
- **FR-3**: 全局默认 prompt 的识别逻辑统一为 `model_code IS NULL AND is_default = True AND is_enabled = True AND is_deleted = False`，消除对 `prompt_code == "Global_Default_Prompt"` 的硬编码依赖。
- **FR-4**: `PromptCache.warm_up()` 需按新的统一逻辑加载全局默认和模型绑定 prompt；`_model_defaults` 因一对一绑定保证天然不会冲突。
- **FR-5**: `dispatcher._build_identity_system()` 函数签名需新增可选参数 `extra_prompt_code: str | None`（或在内部从 session/上下文获取），用于加载前端指定的可选 prompt。
- **FR-6**: AI 对话接口（`POST /chat` 和 `POST /chat/chat/stream`）入参新增可选字段 `prompt_code`。
- **FR-7**: 前端传入的 `prompt_code` 对应的 prompt 必须满足以下条件，否则返回 400 错误：
  1. 存在（未被软删除）
  2. `is_enabled = True`
  3. `model_code IS NULL`（非绑定）
  4. `is_default = False`（非全局默认）
- **FR-8**: system prompt 拼接顺序固定为：
  ```
  身份声明
    ↓
  全局默认 prompt（有则追加）
    ↓
  模型绑定 prompt（有则追加）
    ↓
  前端指定可选 prompt（prompt_code 传入且校验通过、且 content 未重复时追加）
    ↓
  用户自定义 system（有则追加）
  ```
- **FR-9**: 去重规则：当要追加某段 content 前，检查其是否与已拼接 parts 列表中任何一项**完全相等**（字符串全等），相等则跳过。
- **FR-10**: `clear_other_model_defaults`、`clear_global_default` 以及 `is_default` 字段的语义保持不变；但因新的一对一约束，同一 model_code 只会有一条绑定记录，`clear_other_model_defaults` 实际上几乎不会再有多条记录要清的场景。

## Non-Functional Requirements

- **NFR-1**: 应用层校验需要在事务内执行（先 check → 不存在则 insert/update），避免并发情况下的竞态；推荐用 `SELECT ... FOR UPDATE` 或 repository 层先查再写的既有模式。
- **NFR-2**: 所有错误信息需要是明确的中文（或与项目现有风格一致的语言），并返回合适的 HTTP 状态码（校验不通过 → 400，prompt_code 不存在 → 404）。
- **NFR-3**: `_build_identity_system` 新增的 prompt_code 加载逻辑不应显著增加单次请求延迟（建议利用现有 prompt_cache 或在 dispatcher 层一次查完）。
- **NFR-4**: 改造后 `prompt_cache.warm_up` 的耗时和内存占用应与当前持平。

## Constraints

- **Technical**: FastAPI + SQLModel/SQLAlchemy，异步 async/await 风格；现有项目用 MySQL（或 SQLite 做测试）
- **Technical**: prompt_cache 是内存缓存，所有 prompt 增改删需调用 `prompt_cache.refresh(session)` 刷新
- **Technical**: AI 接口 `/chat/stream` 使用 Form 参数（非 JSON body），新增字段需兼容 Form
- **Business**: 保持向后兼容——前端不传 `prompt_code` 时行为与改造前等价（除了全局默认的判断逻辑修正带来的隐式变化）

## Assumptions

- DB 中当前没有脏数据（多条 prompt 绑定同一 model_code）；如有，运维在部署前手动清理
- 全局默认 prompt 在 DB 中能通过 `model_code IS NULL AND is_default = True` 条件唯一命中（与现有 `clear_global_default` 互斥逻辑保持一致）
- 前端可选 prompt 的 content 去重基于字符串全等比较，不做语义理解或模糊匹配
- 用户自定义的 `system` 字段不受 `prompt_code` 参数影响，二者独立传递

## Acceptance Criteria

### AC-1: 创建 prompt 时 model_code 校验
- **Given**: DB 中已存在 prompt A 绑定了 `model_code="deepseek-chat"`
- **When**: 创建 prompt B 且指定 `model_code="deepseek-chat"`
- **Then**: 返回 HTTP 400，message 类似"该模型已被其他提示词绑定"；DB 中不会有第二条 prompt 绑定同一 model_code
- **Verification**: `programmatic`

### AC-2: 创建 prompt 时 model_code 为空不触发校验
- **Given**: DB 中存在任意数量绑定/未绑定的 prompt
- **When**: 创建 prompt 且 `model_code=None`（前端不传）
- **Then**: 正常创建，不受绑定校验约束
- **Verification**: `programmatic`

### AC-3: 更新 prompt 时 model_code 改为已被占用值
- **Given**: prompt A 绑定 `model_code="deepseek-chat"`；prompt B 当前 `model_code=None`
- **When**: 更新 prompt B 的 `model_code="deepseek-chat"`
- **Then**: 返回 HTTP 400；prompt B 的 model_code 保持不变
- **Verification**: `programmatic`

### AC-4: 更新 prompt 时排除自身
- **Given**: prompt A 绑定 `model_code="deepseek-chat"`
- **When**: 更新 prompt A 自身的其他字段（如 name、content），model_code 不变
- **Then**: 正常更新，不会误判"自己和自己冲突"
- **Verification**: `programmatic`

### AC-5: 全局默认判断逻辑统一
- **Given**: DB 中 prompt X 满足 `model_code IS NULL AND is_default=True AND is_enabled=True`
- **When**: 应用启动 warm_up 后调用 `prompt_cache.global_default`
- **Then**: 返回 prompt X，而不是去匹配某个特定 prompt_code 值
- **Verification**: `programmatic`

### AC-6: 对话接口新增 prompt_code 参数
- **Given**: 存在一条满足条件的可选 prompt（`model_code=null, is_default=false, is_enabled=true`）prompt_code="creative_writer"
- **When**: 调用 `POST /chat` 或 `POST /chat/chat/stream`，传入 `prompt_code="creative_writer"`
- **Then**: 最终传给 provider 的 system prompt 中包含该 prompt 的 content，位于模型绑定 prompt 之后、用户 system 之前
- **Verification**: `programmatic`

### AC-7: prompt_code 校验失败返回明确错误
- **Given**: 传入的 `prompt_code` 对应 prompt 满足以下任一条件：已软删除、已禁用、`model_code IS NOT NULL`（绑定了模型）、`is_default=True`（全局默认）
- **When**: 调用 AI 对话接口传入该 prompt_code
- **Then**: 返回 HTTP 400 或 404，message 明确指出原因（如"该提示词已被模型绑定，不可选择"、"该提示词是全局默认，不可选择"）
- **Verification**: `programmatic`

### AC-8: prompt_code 不存在返回 404
- **Given**: 传入的 `prompt_code` 在 DB 中不存在或已软删除
- **When**: 调用 AI 对话接口传入该 prompt_code
- **Then**: 返回 HTTP 404
- **Verification**: `programmatic`

### AC-9: 去重逻辑
- **Given**: 前端指定的 prompt 其 content 恰好与全局默认 prompt 的 content 相同（或与模型绑定 prompt 相同）
- **When**: 调用 AI 对话接口传入该 prompt_code
- **Then**: system prompt 拼接结果中该段 content 只出现一次
- **Verification**: `programmatic`

### AC-10: 不传 prompt_code 时行为等价
- **Given**: 前端调用 AI 对话接口，不传 `prompt_code` 参数
- **When**: 后端处理请求
- **Then**: system prompt 拼接结果为"身份声明 → 全局默认 → 模型绑定 prompt → 用户 system"，与改造前等价（全局默认判断逻辑修正的变化除外）
- **Verification**: `programmatic`

### AC-11: 软删除后的 prompt 不参与绑定校验
- **Given**: prompt A 已软删除（is_deleted=True）且曾绑定 `model_code="deepseek-chat"`
- **When**: 创建新 prompt 绑定 `model_code="deepseek-chat"`
- **Then**: 校验通过，正常创建
- **Verification**: `programmatic`

## Open Questions

- [ ] 是否需要在 DB 层也加唯一约束？比如 `CREATE UNIQUE INDEX ... WHERE model_code IS NOT NULL AND is_deleted = false`（PostgreSQL partial unique index），还是仅应用层校验？spec 按"仅应用层校验"设计，避免 migration 复杂度和 MySQL partial index 不支持的问题。
- [ ] 前端传入的 `prompt_code` 如果同时满足"可选 prompt"和"该 prompt 恰好就是模型绑定的那一条"会怎么样？按 FR-7 规则，绑定了模型的 prompt 不可作为可选 prompt，所以这会返回 400 错误。是否合理？（是的，因为用户需求里明确要求"非绑定"）
- [ ] 去重是在运行时比较字符串，还是可以基于 prompt_code 集合判断（如果同一个 prompt_code 已被加载过）？后者更高效。待实现时确认。
