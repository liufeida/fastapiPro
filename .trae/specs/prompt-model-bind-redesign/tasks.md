# 提示词-模型绑定关系重构 - The Implementation Plan (Decomposed and Prioritized Task List)

## [x] Task 1: PromptCache 统一全局默认判断逻辑
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 修改 `PromptCache.warm_up()` 方法，将全局默认的识别逻辑从硬编码 `prompt_code == "Global_Default_Prompt"` 改为 `model_code is None AND is_default=True`（与 Repository 的 `get_global_default` 保持一致）
  - `_model_defaults` 保持 `prompt.is_default AND prompt.model_code` 的过滤条件不变（一对一约束由 Service 层保证，cache 只负责存储）
  - 新增 `_optional_prompts: dict[str, SystemPrompt]` 缓存字典，存所有满足 `model_code is None AND is_default=False AND is_enabled=True` 的可选 prompt，供后续 Task 3 使用（从 cache 取而非每次查 DB）
  - 新增 `get_optional_by_code(prompt_code: str) -> SystemPrompt | None` 方法
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-1.1: warm_up 后 `cache.global_default` 返回 `model_code IS NULL AND is_default=True` 的那条，而非去匹配特定 prompt_code
  - `programmatic` TR-1.2: `cache.get_optional_by_code("xxx")` 只返回 `model_code IS NULL AND is_default=False` 的 prompt；绑定了模型或设了默认的 prompt_code 查询返回 None
  - `programmatic` TR-1.3: 禁用的 prompt（`is_enabled=False`）不会出现在 `_optional_prompts` 中
  - `programmatic` TR-1.4: `_model_defaults` 只包含 `model_code IS NOT NULL AND is_default=True` 的记录
- **Notes**: 这个改造会让全局默认的判断逻辑和 Repository 层统一。如果 DB 中当前只有 `prompt_code="Global_Default_Prompt"` 那一条记录且它的 `is_default` 不是 True，warm_up 后 `global_default` 会变成 None——这是预期的行为修正，部署前需要运维确认数据。

## [x] Task 2: Prompt Service 层一对一绑定校验
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 新增 Repository 方法 `is_model_code_bound(session, model_code, exclude_id=None) -> bool`：检查是否存在另一条未删除的 prompt 已绑定该 model_code
  - 修改 Service 层 `PromptServices.create()` 和 `PromptServices.update()`：当前端传入 `model_code`（非空非 None）时调用上述校验，已绑定则抛 400 BusinessException
  - 保持现有 `clear_other_model_defaults` / `clear_global_default` 逻辑不变（因一对一约束实际上不会再触发多条清理场景，但保留以防万一）
  - 校验逻辑在 prompt 增/改/删后仍需调用 `prompt_cache.refresh(session)`
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3, AC-4, AC-11
- **Test Requirements**:
  - `programmatic` TR-2.1: 创建 prompt B 绑定已被占用的 model_code → 返回 400
  - `programmatic` TR-2.2: 创建 prompt 不传 model_code → 正常创建
  - `programmatic` TR-2.3: 更新 prompt 的 model_code 改为已被其他 prompt 占用的值 → 返回 400
  - `programmatic` TR-2.4: 更新 prompt 自身其他字段，model_code 不变 → 正常通过（排除自身校验）
  - `programmatic` TR-2.5: 软删除的 prompt 占用的 model_code 不阻断新 prompt 绑定
- **Notes**: 注意和 `is_default` 的关系——新 prompt 如果传了 model_code 同时传了 is_default=True，仍然需要校验绑定冲突（由 model_code 触发）。

## [x] Task 3: Dispatcher 层支持前端 prompt_code 参数 + 拼接去重
- **Priority**: high
- **Depends On**: Task 1, Task 2
- **Description**:
  - `_build_identity_system()` 新增参数 `extra_prompt: SystemPrompt | None`
  - 新增 `_load_optional_prompt(session, prompt_code) -> SystemPrompt | None` 方法：先查 cache（Task 1 新增的 `_optional_prompts`），不存在再查 DB（为了安全降级），并校验：存在、未删除、已启用、`model_code IS NULL`、`is_default=False`；不满足则抛 BusinessException（400/404）
  - 去重逻辑：在拼接 parts 列表时，对每段要追加的 content 检查是否与已在列表中的任何一项**完全相等**（字符串全等），相等则跳过
  - 修改 `AIDispatcher.chat()` 和 `AIDispatcher.chat_stream_with_tools()`：新增参数 `prompt_code: str | None`，在调用 `_build_identity_system()` 前先调 `_load_optional_prompt()`
  - 拼接顺序最终确定为：身份 → 全局默认 → 模型绑定 → 前端可选（prompt_code）→ 用户 system
- **Acceptance Criteria Addressed**: AC-6, AC-7, AC-8, AC-9
- **Test Requirements**:
  - `programmatic` TR-3.1: 传入合法 prompt_code → 最终 system prompt 中包含该段 content，位置在模型绑定 prompt 之后
  - `programmatic` TR-3.2: prompt_code 不存在 → 返回 404
  - `programmatic` TR-3.3: prompt_code 对应 prompt 已绑定模型（model_code 非空）→ 返回 400，message 明确说明
  - `programmatic` TR-3.4: prompt_code 对应 prompt 是全局默认（is_default=True）→ 返回 400，message 明确说明
  - `programmatic` TR-3.5: 去重生效（前端指定 prompt content 与全局默认或模型绑定 prompt content 相同 → 不重复追加）
  - `programmatic` TR-3.6: 不传 prompt_code → 行为与改造前等价（除全局默认判断修正外）
- **Notes**: 这里需要 session 来查 DB（cache 里也没有时）。dispatcher 方法已有 session 参数，可直接传递。

## [x] Task 4: AI 对话接口新增 prompt_code 入参
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - `ChatRequest`（非流式 JSON body）新增字段 `prompt_code: Optional[str] = None`
  - 流式接口 `/chat/chat/stream`（Form 参数）新增 `prompt_code: Optional[str] = Form(None, description="可选的自定义提示词 code，需为非绑定、非全局默认的启用提示词")`
  - 路由层将 prompt_code 传递给 `ai_dispatcher.chat()` 和 `ai_dispatcher.chat_stream_with_tools()`
- **Acceptance Criteria Addressed**: AC-6, AC-10
- **Test Requirements**:
  - `programmatic` TR-4.1: POST /chat body 中传 prompt_code → dispatcher 接收到该值
  - `programmatic` TR-4.2: POST /chat/stream Form 中传 prompt_code → dispatcher 接收到该值
  - `programmatic` TR-4.3: 不传 prompt_code → dispatcher 收到 None，行为不变
- **Notes**: 流式接口用 Form，非流式用 JSON body，注意两种写法都要改。

## [x] Task 5: 端到端测试 + Prompt CRUD 回归验证
- **Priority**: medium
- **Depends On**: Task 1, Task 2, Task 3, Task 4
- **Description**:
  - 编写集成测试覆盖：prompt CRUD 一对一校验 → AI 接口传入/不传 prompt_code → 全链路 system prompt 拼接正确 → 错误场景返回明确 message
  - 可复用项目已有的 test infrastructure（如果有 pytest + httpx client）
- **Acceptance Criteria Addressed**: AC-1 ~ AC-11（全部覆盖）
- **Test Requirements**:
  - `programmatic` TR-5.1: 端到端测试通过（所有 AC 对应的场景）
  - `programmatic` TR-5.2: 现有 prompt 管理接口测试（如果有）不受影响
  - `programmatic` TR-5.3: 现有 AI 对话接口测试（如果有）不传 prompt_code 的场景通过
- **Notes**: 运行项目现有测试套件，确认没有回归。
