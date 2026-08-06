# Tasks

## 一、数据模型与迁移
- [ ] Task 1: 创建 `ai_model_config` 表模型与 schema
  - [ ] SubTask 1.1: 新建 `app/models/ai_model_config.py`，定义 `AIModelConfigBase` / `AIModelConfig`(table=True) / `AIModelConfigCreate` / `AIModelConfigUpdate` / `AIModelConfigReo` / `QueryRequest` / `PageResult`
    - 字段严格按 spec.md 表结构：id(uuid hex PK)、provider_code、model_code、model_name、api_key、base_url、extra_config(JSON)、supports_thinking/Tools/Stream/Vision、max_tokens、temperature、is_enabled、is_default、sort_order、description、created_at、updated_at、is_deleted
    - `AIModelConfigReo` 带 `model_config = ConfigDict(from_attributes=True)`，`api_key` 字段保留（用于脱敏展示）
    - `AIModelConfigUpdate` 所有字段 Optional，支持局部更新；空字符串归一化为 None（参考 `UsersUpdate.normalize_update_text`）
    - 复用项目分页约定：`PageParams` / `QueryRequest`（含 keyword/provider_code/is_enabled 过滤）/ `PageResult`（Generic[T]）
  - [ ] SubTask 1.2: 在 `alembic/env.py` 导入 `AIModelConfig`，确保 autogenerate 可识别
  - [ ] SubTask 1.3: 生成 Alembic 迁移文件 `alembic/versions/xxx_add_ai_model_config.py`，建表 + 预置两条种子数据（DeepSeek 与 Ollama，从现有环境变量/常量迁移值）

## 二、AI Provider 抽象层（可与 Task 1 部分并行）
- [x] Task 2: 搭建 Provider 抽象与注册表
  - [ ] SubTask 2.1: 新建 `app/services/ai/__init__.py`
  - [ ] SubTask 2.2: 新建 `app/services/ai/base.py`，定义 `AIProvider` 抽象基类（抽象方法 `chat` / `chat_stream` / `chat_stream_with_tools`）、`ToolEvent` dataclass、`StreamChunk` 类型别名（与现有 `app/services/deepseek.py` 的 ToolEvent 保持兼容）
  - [ ] SubTask 2.3: 新建 `app/services/ai/registry.py`，实现 `ProviderRegistry`：`register(provider_code, provider)` / `get(provider_code) -> AIProvider`，未注册时抛 `BusinessException(code=500, message="未注册的模型提供商: {code}")`；导出单例 `provider_registry`
  - [ ] SubTask 2.4: 新建 `app/services/ai/sse.py`，提取 `build_sse(event, data) -> ServerSentEvent`（迁移自 `app/api/v1/deepseek.py` 的 `_sse`），data 强制 JSON、`ensure_ascii=False`

## 三、Provider 实现（依赖 Task 1 + Task 2）
- [ ] Task 3: 实现 `DeepSeekProvider`
  - [ ] SubTask 3.1: 新建 `app/services/ai/deepseek_provider.py`，实现 `AIProvider` 接口
  - [ ] SubTask 3.2: `thinking=false` 路径：复用现有 `deepseek_service` 的 LangChain `ChatDeepSeek` 逻辑，但 api_key/base_url/model 改为从传入的 `AIModelConfig` 读取（不读环境变量）
  - [ ] SubTask 3.3: `thinking=true` 路径：**必须**走原生 httpx 直接消费 DeepSeek SSE 流，从 `delta.reasoning_content` 提取思考内容产出 `ToolEvent(type="thinking")`，禁止用 LangChain（遵守 project_memory 硬约束）
  - [ ] SubTask 3.4: `chat_stream` 与 `chat_stream_with_tools` 两个入口均支持 thinking 提取；`enable_search=False` 时退化为纯流式
  - [ ] SubTask 3.5: 在模块加载时调用 `provider_registry.register("deepseek", DeepSeekProvider())`
- [ ] Task 4: 实现 `OllamaProvider`
  - [ ] SubTask 4.1: 新建 `app/services/ai/ollama_provider.py`，实现 `AIProvider` 接口
  - [ ] SubTask 4.2: 从 `AIModelConfig.base_url` 读取 ollama host，从 `extra_config.cloud_url` / `extra_config.api_key` 读取云端配置（替代现有文件常量）
  - [ ] SubTask 4.3: 流式输出统一为 JSON：每条 chunk 包装为 `{"content": "..."}`，结束发 `Done: {}`，错误发 `error: {"message":"..."}`
  - [ ] SubTask 4.4: Ollama 默认 `supports_thinking=False`、`supports_tools=False`，调用时若传 `thinking=true` 由 dispatcher 拦截报错
  - [ ] SubTask 4.5: 在模块加载时调用 `provider_registry.register("ollama", OllamaProvider())`

## 四、调度器（依赖 Task 1 + Task 2 + Task 3 + Task 4）
- [ ] Task 5: 实现 `ai_dispatcher`
  - [ ] SubTask 5.1: 新建 `app/services/ai/dispatcher.py`，实现 `AIDispatcher`：
    - `resolve(model_code, session) -> AIModelConfig`：查库，校验 `is_enabled=True AND is_deleted=False`，否则抛 `BusinessException(code=404, message="模型不可用或未配置")`
    - `check_capability(config, thinking, enable_search)`：`thinking=true` 但 `supports_thinking=False` 抛 400；`enable_search=True` 但 `supports_tools=False` 抛 400
    - `chat(session, model_code, prompt, system, thinking) -> str`
    - `chat_stream_with_tools(session, model_code, prompt, system, thinking, enable_search, file_context) -> AsyncIterator[StreamChunk]`
  - [ ] SubTask 5.2: 导出单例 `ai_dispatcher`
  - [ ] SubTask 5.3: 在 `app/services/ai/__init__.py` 中导入 `deepseek_provider` 与 `ollama_provider`，确保注册副作用执行

## 五、AI 模型配置 CRUD（依赖 Task 1）
- [x] Task 6: 实现 Repository 层
  - [ ] SubTask 6.1: 新建 `app/repository/ai_model_config.py`，实现 `AIModelConfigRepository`：
    - `get_by_id(session, id)`（过滤 is_deleted）
    - `get_by_model_code(session, model_code)`（路由用，含 provider_code）
    - `exists_by_provider_and_code(session, provider_code, model_code, exclude_id=None) -> bool`（唯一性校验）
    - `create(session, data: dict) -> AIModelConfig`
    - `update(session, id, update_data: dict) -> AIModelConfig`
    - `soft_delete(session, id) -> AIModelConfig`
    - `list_enabled(session) -> list[AIModelConfig]`（is_enabled=True AND is_deleted=False，按 sort_order asc, created_at desc）
    - `list_paginated(session, offset, limit, **filters) -> list[AIModelConfig]` + `count(session, **filters) -> int`（参考 `UsersRepository._apply_filters`）
    - `clear_other_defaults(session, exclude_id) -> None`（默认模型互斥）
  - [ ] SubTask 6.2: 导出单例 `ai_model_config_repository`
- [x] Task 7: 实现 Service 层
  - [ ] SubTask 7.1: 新建 `app/services/ai_model_config.py`，实现 `AIModelConfigServices`：
    - `create(session, data: AIModelConfigCreate)`：唯一性校验 → 若 `is_default=True` 先 `clear_other_defaults` → 落库 → 返回 `AIModelConfigReo`（api_key 脱敏）
    - `get_by_id(session, id)`：返回脱敏 Reo
    - `list_paginated(session, query: QueryRequest) -> PageResult[AIModelConfigReo]`：脱敏
    - `list_enabled(session) -> list[AIModelConfigReo]`：**响应中 exclude api_key**
    - `update(session, id, data: AIModelConfigUpdate)`：`exclude_unset` → 唯一性校验（若改了 code）→ 默认互斥（若改 is_default=True）→ 落库 → 脱敏 Reo
    - `delete(session, id)`：软删除；若删的是默认模型，提示前端重新指定（不自动转移，避免误判）
    - `mask_api_key(key: str | None) -> str | None`：脱敏工具，如 `sk-xxxx5678` → `sk-****5678`；None 透传
  - [ ] SubTask 7.2: 导出单例 `ai_model_config_services`
- [ ] Task 8: 实现路由层
  - [ ] SubTask 8.1: 新建 `app/api/v1/ai_model_config.py`，挂 6 个接口：
    - POST `/ai-models`（createAIModelConfig，response_model=`ResponseModel[AIModelConfigReo]`）
    - POST `/ai-models/list`（getAIModelConfigList，response_model=`ResponseModel[PageResult[AIModelConfigReo]]`）
    - GET `/ai-models/{id}`（getAIModelConfigById）
    - PATCH `/ai-models/{id}`（updateAIModelConfig）
    - DELETE `/ai-models/{id}`（deleteAIModelConfig）
    - GET `/ai-models/enabled`（getEnabledAIModels，response_model=`ResponseModel[list[AIModelConfigReo]]`，exclude api_key）
  - [ ] SubTask 8.2: 所有接口用 `SessionDeep` 依赖注入，响应走 `Execute.response()`

## 六、通用 AI 对话入口（依赖 Task 5）
- [x] Task 9: 实现通用 AI 路由
  - [ ] SubTask 9.1: 新建 `app/api/v1/ai.py`，挂 3 个接口：
    - GET `/ai/health`（aiHealthCheck）：返回注册的 provider 列表 + 启用模型数量
    - POST `/ai/chat`（aiChat）：JSON body `{model, prompt, system?, thinking?}`，调用 `ai_dispatcher.chat`
    - POST `/ai/chat/stream`（aiChatStream，response_class=EventSourceResponse）：Form 入参 `model/prompt/system/thinking/enable_search/files`，调用 `ai_dispatcher.chat_stream_with_tools`，用 `build_sse` 输出统一事件流
  - [ ] SubTask 9.2: 流式入口复用 `app/api/v1/deepseek.py` 的事件转换逻辑（ToolEvent → SSE），统一用 `build_sse`；错误兜底发 `error` 事件
  - [ ] SubTask 9.3: 入口前调用 `ai_dispatcher.check_capability` 做能力校验

## 七、路由挂载与收尾
- [x] Task 10: 注册新路由
  - [ ] SubTask 10.1: 在 `app/api/v1/api.py` 导入并挂载 `ai.router`（prefix=`/ai`, tags=`["AI"]`）与 `ai_model_config.router`（prefix=`/ai-models`, tags=`["AI Model Config"]`），均不加 `get_current_user` 依赖
  - [ ] SubTask 10.2: 在 `app/main.py` 或 `app/services/ai/__init__.py` 确保 provider 注册副作用在应用启动时执行（导入即注册）

## 八、验证
- [x] Task 11: 自测验证（静态验证 50 项通过 + 导入检查通过 + 2 个 bug 已修复；运行时验证需用户在本地环境执行）
  - [ ] SubTask 11.1: 启动服务，确认无导入错误，`/api/docs` 能看到新增的 `AI` 与 `AI Model Config` 两组接口
  - [ ] SubTask 11.2: 跑迁移 `alembic upgrade head`，确认建表成功且种子数据写入
  - [ ] SubTask 11.3: 调 `GET /ai-models/enabled` 验证返回列表且不含 `api_key`
  - [ ] SubTask 11.4: 调 `POST /ai/chat/stream` 传 `model=deepseek-v4-flash`、`thinking=true`，验证 SSE 流含 `thinking` + `content` + `Done` 事件
  - [ ] SubTask 11.5: 调 `POST /ai/chat/stream` 传一个 `supports_thinking=False` 的模型 + `thinking=true`，验证返回 400 业务异常
  - [ ] SubTask 11.6: 调 `POST /ai-models` 创建重复 `model_code`，验证返回 400 "该模型代码已存在"

# Task Dependencies
- Task 1（模型）是基础，Task 2（抽象层）可与之并行
- Task 3、Task 4 依赖 Task 1 + Task 2
- Task 5 依赖 Task 3 + Task 4
- Task 6 依赖 Task 1
- Task 7 依赖 Task 6
- Task 8 依赖 Task 7
- Task 9 依赖 Task 5
- Task 10 依赖 Task 8 + Task 9
- Task 11 依赖 Task 10
- 可并行批次：{Task 1, Task 2} → {Task 3, Task 4, Task 6} → {Task 5, Task 7} → {Task 9, Task 8} → Task 10 → Task 11
