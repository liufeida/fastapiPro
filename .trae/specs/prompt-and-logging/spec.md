# Prompt 工程管理 + 接口日志 - 产品需求文档

## Overview
- **Summary**: 为 FastAPI 后端新增两大基础设施模块：① 系统提示词（System Prompt）的数据库化管理与动态注入；② 全链路接口日志（HTTP 请求/响应 + AI LLM 调用）的记录与查询。所有功能遵循项目现有的 `models → repository → services → api` 四层分层架构。
- **Purpose**: 解决当前提示词硬编码不可运营、调试 LLM 黑盒调用不透明的痛点。让开发者/运营可在前端 CRUD 微调系统提示词，并能看到每次 API 请求和 AI 调用的完整入参、出参与耗时。
- **Target Users**: 后端开发者（调试与问题定位）、前端开发者（消费 CRUD 接口）、产品/运营（在前端面板微调 System Prompt、查看接口日志）。

---

## 第一部分：System Prompt 工程管理

### Goals
- 将 System Prompt 从代码硬编码迁移到数据库，支持 CRUD
- Prompt 可按 `model_code` 绑定，也可作为全局默认 Prompt
- Prompt 支持启停、版本（soft delete + 默认标记互斥）
- Dispatcher 层自动合并 DB Prompt 与前端传入的 `system` 参数

### Non-Goals (Out of Scope)
- 不做 Prompt 模板变量替换（如 `{{user_name}}`）——先存纯文本
- 不做 Prompt 灰度发布 / A/B 测试
- 不做 Prompt 的 Git 版本控制（用软删除和 updated_at 回溯即可）
- 不做前端 UI——仅提供后端 CRUD API

### Background & Context
- 当前 `dispatcher.py` 的 `_build_identity_system` 硬编码了身份 system prompt（`你是 {model_name}（model_code: {model_code}）。当前日期时间: ...`），用户前端传入的 `system` 追加在后面
- 用户希望把这块"系统提示词"也做成可配置、可 CRUD 的
- **性能考量**：AI 请求是高频路径，不能每次都查 DB。采用「DB 存储 + 内存 dict 缓存 + 启动加载 + 写入时刷新」策略

### Functional Requirements（Prompt 模块）

- **FR-P1**: Prompt 数据表结构
  - `id` (uuid)
  - `name` (str, 展示名称，如"DeepSeek 默认对话提示词")
  - `prompt_code` (str, 唯一代码，如 `deepseek_chat_default`)
  - `content` (text, 提示词正文，可多行)
  - `model_code` (str | None, 绑定的 AI 模型；None 表示全局默认)
  - `is_default` (bool, 同一 model_code 维度 + 全局维度各一个 True)
  - `is_enabled` (bool, 启停开关)
  - `sort_order` (int)
  - `description` (str | None)
  - `is_deleted` / `created_at` / `updated_at`

- **FR-P2**: Prompt CRUD API（遵循现有 `ai_model_config` 路由风格）
  - `POST /v1/prompts` 创建（唯一性校验 prompt_code，默认标记互斥）
  - `POST /v1/prompts/list` 分页列表（keyword 模糊 + model_code 精确 + is_enabled 过滤）
  - `GET /v1/prompts/{id}` 单条查询
  - `PATCH /v1/prompts/{id}` 局部更新
  - `DELETE /v1/prompts/{id}` 软删除
  - `GET /v1/prompts/active` 获取所有启用的 Prompt（前端配置面板用，不含 is_deleted）

- **FR-P3**: Dispatcher 集成
  - 改造 `_build_identity_system`：优先从 PromptService 内存缓存取匹配的 Prompt（先 model_code 精确匹配，再全局默认），再叠加身份前缀（日期时间），最后拼接用户传入的 system
  - 缓存刷新：每次 Prompt 增/改/删时，Service 层调用 `prompt_cache.refresh()`
  - 启动加载：在 `lifespan` 事件里调用一次 `prompt_cache.warm_up()`

---

## 第二部分：接口日志

### Goals
- **HTTP API 日志**：记录每次请求的方法、路径、前端传入参数（query + body）、响应状态码、耗时、返回数据
- **AI LLM 调用日志**：记录 model_code、发给 LLM 的完整 messages（含 system）、LLM 返回内容、token 消耗、thinking 内容、耗时、错误信息
- **CRUD + 分页查询**：前端可列表查看、按条件筛选（时间范围、接口路径、model_code、状态码、是否报错）、按 id 查看详情
- **异步写入**：日志写入不能阻塞主请求，Fire-and-Forget 或内存队列 + 后台 flush

### Non-Goals (Out of Scope)
- 不做日志的前端实时推送（WebSocket / SSE 推送日志流）
- 不做日志自动归档 / 过期清理策略（由用户手动 DELETE 或 DBA 处理）
- 不做 Prometheus / Grafana 指标导出
- 不做前端 UI——仅提供后端 CRUD API
- SSE 流式响应的 HTTP 完整 body 无法在中间件层面捕获（只能存已发送的 chunk 摘要），但 **AI LLM 调用层面** 会记录完整内容（因为是在 provider 层埋点）

### Background & Context
- 当前中间件只记录了 `X-Process-Time` 响应头，无持久化
- AI 调用的完整 messages 和响应内容目前只在 logger.info 里打了一行摘要，无法追溯
- SSE 流式响应的中间件拦截有天然困难（response body 是 StreamingResponse，不能提前 read）

### Functional Requirements（日志模块）

- **FR-L1**: 日志分两张表
  - `api_access_log`（HTTP API 访问日志）
    - `id` (uuid)
    - `trace_id` (str, 请求级唯一标识，贯穿 HTTP + AI 日志关联)
    - `method` (str, GET/POST/...)
    - `path` (str, 请求路径如 `/api/v1/ai/chat`)
    - `query_params` (json, query string 序列化)
    - `request_body` (text, 前端传入的 body 原始字符串，SSE 时为摘要)
    - `response_status` (int, HTTP 状态码)
    - `response_body` (text, 非流式时为完整响应 JSON 字符串；流式时为 `"(streaming)"` 或首个 chunk 摘要)
    - `duration_ms` (float, 请求总耗时)
    - `is_streaming` (bool, 是否 SSE/流式)
    - `is_error` (bool, 是否异常）
    - `error_message` (text | None, 异常消息或堆栈）
    - `ip` (str | None, 客户端 IP）
    - `user_agent` (str | None）
    - `created_at`
  - `ai_chat_log`（AI LLM 调用日志）
    - `id` (uuid)
    - `trace_id` (str, 关联 api_access_log)
    - `model_code` (str)
    - `provider_code` (str)
    - `user_prompt` (text, 前端传入的原始 prompt)
    - `system_prompt` (text, 实际发给 LLM 的 system——包含 Prompt 表 + 身份前缀 + 用户 system)
    - `messages` (text, 完整的 messages 数组 JSON 字符串)
    - `response_content` (text, LLM 返回的完整内容，流式时拼接所有 chunk)
    - `thinking_content` (text | None, thinking 模式下的推理链)
    - `input_tokens` (int | None)
    - `output_tokens` (int | None)
    - `duration_ms` (float, AI 调用耗时)
    - `thinking_ms` (float | None, thinking 阶段耗时)
    - `is_error` (bool)
    - `error_message` (text | None)
    - `created_at`

- **FR-L2**: 日志记录埋点
  - HTTP 层：扩展 `middleware.py`，新增 `api_access_log_middleware`——用中间件拦截请求/响应，非流式直接读 body + response；流式时用 `StreamingResponse` 包装器收集 chunk 内容
  - AI 层：在 `dispatcher.py` 的 `chat` / `chat_stream_with_tools` 里，用一个 `AIChatLogger` 服务类埋点——chat 方法直接记录；chat_stream_with_tools 在 async generator 外层包一层，收集 chunk 后 flush
  - **trace_id 传递**：从 HTTP 中间件生成一个 uuid 作为 trace_id，通过 `contextvars` 传递到 AI 层

- **FR-L3**: 日志 CRUD 查询 API
  - `POST /v1/logs/api/list` HTTP 访问日志分页列表（支持 trace_id 精确 + path 模糊 + method + response_status + is_error + 时间范围筛选）
  - `GET /v1/logs/api/{id}` HTTP 日志详情
  - `POST /v1/logs/ai/list` AI 调用日志分页列表（支持 trace_id + model_code + provider_code + is_error + 时间范围）
  - `GET /v1/logs/ai/{id}` AI 日志详情
  - `DELETE /v1/logs/api/{id}` 删除单条（物理删）
  - `DELETE /v1/logs/ai/{id}` 删除单条

- **FR-L4**: 异步写入保障
  - 日志 Service 提供 `enqueue()` 方法，将日志数据放入 asyncio.Queue
  - 后台有一个 flush task 每 2s 或队列积压 > 50 条时批量写入
  - 应用关闭前（lifespan 的 finally）强制 flush 剩余队列
  - 主请求不 await 日志写入——fire-and-forget

- **FR-L5**: 敏感数据脱敏
  - `request_body` 和 `messages` 中的 API Key、Authorization header 不记录（或者只存脱敏值）
  - AI Provider 的 api_key 永远不进日志

---

## Non-Functional Requirements（通用）

- **NFR-1**: 严格遵循项目现有分层——每个新模块都有 `models/*.py`、`repository/*.py`、`services/*.py`、`api/v1/*.py`
- **NFR-2**: 遵循现有代码风格——单例导出、`Execute.response` 包裹响应、`PageResult` 分页、soft delete 模式
- **NFR-3**: 数据库迁移——新建表需要生成 alembic migration
- **NFR-4**: 类型安全——所有入参/出参都有 SQLModel/Pydantic 模型，禁止 `dict` 裸奔
- **NFR-5**: 日志写入异步化——不能因日志写入拖慢主请求（AI 高频场景尤其关键）

---

## Constraints

- **Technical**: 项目使用 FastAPI 0.135+、SQLModel + asyncpg、PostgreSQL 本地库；现有中间件模式为 `register_middleware_handles(app)`
- **Business**: 用户明确要求"前端也可以看到"，所以 Prompt 和 Log 模块都必须有完整的 CRUD 查询接口
- **Dependencies**: 依赖现有的 `dispatcher.py`、`ai_model_config` 模块做集成

---

## Assumptions

- 假设 PostgreSQL 数据库已在本地运行且当前用户有 DDL 权限（alembic migration 能执行）
- 假设 prompt 的 content 内容不会超过 text 类型上限（PostgreSQL text 约 1GB 上限，完全够用）
- 假设日志表的 volume 在可接受范围内——如果后期数据量爆炸，需要用户加 TTL 策略（不在本次 scope）
- 假设 `contextvars` 在 FastAPI async 中间件 + async generator 链路中能正确传递 trace_id（Python 3.7+ 标准库，可靠）

---

## Acceptance Criteria

### AC-1: Prompt CRUD 全流程可用
- **Given**: 数据库中有 Prompt 表，应用启动完成
- **When**: 通过 API 创建/查询/更新/删除 Prompt
- **Then**: 所有操作符合预期，响应格式为 `ResponseModel[T]`，默认标记互斥生效，软删除不可查
- **Verification**: `programmatic`

### AC-2: Dispatcher 自动注入 DB Prompt
- **Given**: 数据库存在一条 `model_code=deepseek-v4-flash, is_enabled=True, is_default=True` 的 Prompt
- **When**: 调用 AI chat 接口，前端不传 system
- **Then**: 实际发给 LLM 的 messages 中 system 内容包含 DB Prompt + 身份前缀
- **Verification**: `programmatic`

### AC-3: Prompt 缓存正确刷新
- **Given**: 应用启动后已 warm up 缓存
- **When**: 通过 API 更新某条 Prompt 的 content
- **Then**: 下一次 AI 调用时，拿到的是新 content（无需重启）
- **Verification**: `programmatic`

### AC-4: HTTP API 日志完整记录
- **Given**: 应用运行中，有请求进来
- **When**: 访问 `/api/v1/ai/chat` 等非流式接口
- **Then**: `api_access_log` 表新增一条记录，method/path/request_body/response_status/response_body/duration_ms 都有值
- **Verification**: `programmatic`

### AC-5: AI LLM 调用日志完整记录
- **Given**: AI 调用正常完成
- **When**: 调用 dispatcher.chat() 或 chat_stream_with_tools()
- **Then**: `ai_chat_log` 表新增一条，包含完整 messages、response_content、duration_ms、trace_id
- **Verification**: `programmatic`

### AC-6: trace_id 贯穿 HTTP → AI
- **Given**: 一次完整的 AI 请求链路
- **When**: HTTP 中间件生成 trace_id 并传递给 AI 层
- **Then**: 对应的 `api_access_log` 和 `ai_chat_log` 记录有相同的 trace_id
- **Verification**: `programmatic`

### AC-7: 异步写入不阻塞主请求
- **Given**: 日志队列为空
- **When**: 高频请求进来（模拟 10 req/s）
- **Then**: 主请求的响应耗时不受日志写入影响（或影响 < 5ms）
- **Verification**: `programmatic`

### AC-8: API Key 不进日志
- **Given**: 任何包含 api_key 或 Authorization 的请求
- **When**: 日志被写入
- **Then**: request_body/messages/error_message 中不出现明文 API Key
- **Verification**: `programmatic`

### AC-9: 日志查询接口正常
- **Given**: 日志表中有数据
- **When**: 通过分页列表接口查询，带筛选条件
- **Then**: 返回 `PageResult`，total/pages 正确，筛选条件生效
- **Verification**: `programmatic`

### AC-10: 代码风格一致性
- **Given**: 新增的所有文件
- **When**: 与现有 `ai_model_config` 模块对比分层结构、命名、单例导出、响应格式
- **Then**: 风格一致，无明显违和
- **Verification**: `human-judgment`

---

## Open Questions

- [ ] 是否需要前端传入自定义 system 时 **覆盖** DB Prompt？目前设计是 **追加**（DB Prompt 在前，用户 system 在后），但也可以考虑让 DB Prompt 当"固定底座"用户追加
- [ ] 日志是否需要记录 **请求中的文件上传**（multipart form-data 的 file 内容）？暂时不做，FR-L1 只考虑 JSON body
- [ ] Prompt 是否需要支持 **变量占位符**（如 `{date}` 自动替换）？暂不做，用户反馈后再加
