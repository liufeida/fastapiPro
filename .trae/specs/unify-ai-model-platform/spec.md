# 统一多 AI 模型接入平台 Spec

## Why
项目当前已接入 DeepSeek 与 Ollama 两类大模型，但二者各自为政：DeepSeek 的配置从环境变量读取、走 LangChain + 原生 httpx 混合路径；Ollama 的配置硬编码在路由文件常量里、直接在路由层裸调 httpx，且 SSE 事件格式与 DeepSeek 不一致（前者 JSON、后者纯文本）。随着后续要接入 OpenAI / Anthropic / 通义千问等更多模型，缺少统一抽象会导致配置散乱、SSE 格式串味、前端需要按 provider 调不同接口、模型无法动态启停。

本规范要解决两件事：
1. 在后端建立一套**统一的 AI 模型调用抽象**（Provider 接口 + 注册表 + 通用入口路由），根据前端传入的 `model_code` 自动路由到对应实现，SSE 事件格式全平台统一。
2. 提供一套 **AI 接口配置 CRUD**，让模型配置（api_key、base_url、能力开关等）落库可管理，前端可直接拉取可用模型列表。

## What Changes

### 一、通用 AI 调用抽象层（新增）
- 新增 `app/services/ai/base.py`：定义 `AIProvider` 抽象基类、`StreamChunk` / `ToolEvent` 统一数据类型。
- 新增 `app/services/ai/registry.py`：`ProviderRegistry` 注册表，按 `provider_code` 注册与获取 Provider 实例（单例）。
- 新增 `app/services/ai/deepseek_provider.py`：`DeepSeekProvider`，复用现有 `deepseek_service` 的核心逻辑（含 `thinking=true` 走原生 httpx 的硬约束），但 api_key / base_url / model 改为从 `AIModelConfig` 实例读取。
- 新增 `app/services/ai/ollama_provider.py`：`OllamaProvider`，重写现有 ollama 逻辑，统一走 Provider 接口，SSE 输出 JSON 格式（与 DeepSeek 对齐）。
- 新增 `app/services/ai/dispatcher.py`：`ai_dispatcher`，根据 `model_code` 查库 → 拿到 `provider_code` → 从注册表取 Provider → 调用，并做能力校验（如配置 `supports_thinking=False` 却传 `thinking=true` 则报错）。
- 新增 `app/api/v1/ai.py`：通用 AI 入口路由（流式 / 非流式 / 健康检查），SSE 事件格式沿用现有 DeepSeek 的 `thinking/content/tool/tool_result/Done/error`，data 一律 JSON。
- 统一 SSE 序列化工具：把 `app/api/v1/deepseek.py` 里的 `_sse` 提取到 `app/services/ai/sse.py`，供所有 Provider 复用。

### 二、AI 模型配置 CRUD（新增）
- 新增 `app/models/ai_model_config.py`：`AIModelConfig` 表模型 + `AIModelConfigCreate/Update/Reo` + 分页 `QueryRequest/PageResult`。
- 新增 `app/repository/ai_model_config.py`：`AIModelConfigRepository`，含唯一性校验（`provider_code + model_code`）。
- 新增 `app/services/ai_model_config.py`：`AIModelConfigServices`，编排 CRUD，处理 api_key 脱敏、默认模型互斥（同一时刻仅一个 `is_default=True`）。
- 新增 `app/api/v1/ai_model_config.py`：CRUD 路由 + `GET /ai-models/enabled`（前端拉取可用模型列表，剔除 `api_key`）。
- 新增 Alembic 迁移：建 `ai_model_config` 表，并预置 DeepSeek 与 Ollama 两条种子数据（从现有环境变量/常量迁移）。

### 三、旧代码兼容处理（非破坏性过渡）
- **保留** `app/api/v1/deepseek.py` 与 `app/services/deepseek.py` 现有接口不动（前端存量调用不中断），但其内部逐步改为委托给 `DeepSeekProvider`（本 spec 仅声明意图，具体迁移在后续 change 推进，避免一次性改动过大）。
- **保留** `app/api/v1/ollama.py` 现有接口不动，同上。
- 新增通用入口 `/ai/chat/stream` 与 `/ai/chat` 作为前端新功能的推荐入口。
- **BREAKING**（仅对新增路由内部约束）：所有新接入的模型必须通过 Provider 抽象注册，禁止再在 `app/api/v1/` 下新增裸调 httpx 的模型路由。

## Impact
- Affected specs: 无（首次建立 AI 平台基线）
- Affected code:
  - 新增：`app/services/ai/`（base/registry/dispatcher/deepseek_provider/ollama_provider/sse）、`app/api/v1/ai.py`、`app/models/ai_model_config.py`、`app/repository/ai_model_config.py`、`app/services/ai_model_config.py`、`app/api/v1/ai_model_config.py`、`alembic/versions/xxx_add_ai_model_config.py`
  - 修改：`app/api/v1/api.py`（注册新路由）、`alembic/env.py`（导入新模型以支持 autogenerate）
  - 不动：`app/api/v1/deepseek.py`、`app/services/deepseek.py`、`app/api/v1/ollama.py`（保持向后兼容）

## ADDED Requirements

### Requirement: 统一 AI Provider 抽象
系统 SHALL 提供一个抽象基类 `AIProvider`，所有大模型接入 MUST 通过实现该基类注册到 `ProviderRegistry`，禁止在路由层裸调第三方 HTTP。

每个 Provider 实现以下方法（均为 async）：
- `chat(config, prompt, system, thinking) -> str`
- `chat_stream(config, prompt, system, thinking) -> AsyncIterator[StreamChunk]`
- `chat_stream_with_tools(config, prompt, system, thinking, enable_search, file_context) -> AsyncIterator[StreamChunk]`

其中 `config: AIModelConfig` 携带该模型的运行期配置（api_key/base_url/model_code/extra_config 等）。

#### Scenario: 已注册的 Provider 被正确路由
- **WHEN** 前端调用 `POST /ai/chat/stream`，body 中 `model="deepseek-v4-flash"`
- **THEN** `ai_dispatcher` 查库得到 `provider_code="deepseek"`，从注册表取 `DeepSeekProvider`，调用其 `chat_stream_with_tools`，按统一 SSE 事件格式输出

#### Scenario: 未注册的 Provider 报错
- **WHEN** 前端传入 `model_code` 在库中不存在或 `is_enabled=False`
- **THEN** 抛出 `BusinessException(code=404, message="模型不可用或未配置")`

#### Scenario: 能力不匹配报错
- **WHEN** 前端传 `thinking=true`，但目标模型 `supports_thinking=False`
- **THEN** 抛出 `BusinessException(code=400, message="该模型不支持思考模式")`

### Requirement: 统一 SSE 事件格式
所有 Provider 的流式输出 MUST 复用 `app/services/ai/sse.py` 的 `build_sse(event, data)` 工具，事件类型与 data 结构如下：

| event | data 结构 | 说明 |
|---|---|---|
| `thinking` | `{"reasoning": "..."}` | 思考内容块（仅 thinking=true 时出现） |
| `content` | `{"content": "..."}` | 回答内容块 |
| `tool` | `{"name": "...", "args": {...}}` | 模型决定调用工具 |
| `tool_result` | `{"name": "...", "result": "..."}` | 后端执行工具结果 |
| `Done` | `{}` | 流结束 |
| `error` | `{"message": "...", "code": 500}` | 流内错误 |

data 一律 `json.dumps(..., ensure_ascii=False)`，中文不转义。

#### Scenario: Ollama 流式输出与 DeepSeek 格式一致
- **WHEN** 前端调用 `/ai/chat/stream` 传 `model="ollama-deepseek-r1-8b"`
- **THEN** 收到的 SSE 事件 data 为 JSON 字符串，`content` 事件结构为 `{"content": "..."}`，与 DeepSeek 完全一致

### Requirement: DeepSeek Provider 保留 thinking 原生 httpx 路径
`DeepSeekProvider` 在 `thinking=true` 时 MUST 走原生 httpx 直接消费 DeepSeek SSE 流并从 `delta.reasoning_content` 提取思考内容，禁止使用 LangChain `ChatOpenAI`/`ChatDeepSeek`（因其会清除 `reasoning_content` 字段）。`thinking=false` 时可继续走 LangChain 路径。`chat_stream` 与 `chat_stream_with_tools` 两个入口均须支持该逻辑。

#### Scenario: thinking=true 走原生 httpx
- **WHEN** 前端传 `thinking=true` 调用 DeepSeek 模型
- **THEN** 后端使用 httpx 直接请求 DeepSeek API，从每个 SSE chunk 的 `delta.reasoning_content` 提取思考内容，产出 `ToolEvent(type="thinking", ...)` 事件

### Requirement: AI 模型配置表
系统 SHALL 新增 `ai_model_config` 表，字段如下：

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | str (uuid hex) | PK | 主键 |
| provider_code | str | NOT NULL | 提供商代码：deepseek/ollama/openai/anthropic/qwen 等 |
| model_code | str | NOT NULL, UNIQUE(软删内) | 模型唯一代码，用于路由 |
| model_name | str | NOT NULL | 展示名称 |
| api_key | str | NULL | API 密钥（响应脱敏） |
| base_url | str | NULL | API 基础地址 |
| extra_config | JSON | NULL | 提供商特有配置（如 ollama 的 host、cloud_url） |
| supports_thinking | bool | default False | 支持思考模式 |
| supports_tools | bool | default False | 支持工具调用 |
| supports_stream | bool | default True | 支持流式 |
| supports_vision | bool | default False | 支持视觉 |
| max_tokens | int | NULL | 最大 tokens |
| temperature | float | NULL | 默认温度 |
| is_enabled | bool | default True | 是否启用 |
| is_default | bool | default False | 是否默认模型 |
| sort_order | int | default 0 | 排序权重（小在前） |
| description | str | NULL | 描述 |
| created_at | datetime(tz) | NOT NULL | 创建时间 |
| updated_at | datetime(tz) | NOT NULL | 更新时间 |
| is_deleted | bool | default False | 软删除 |

唯一性约束：`(provider_code, model_code)` 在 `is_deleted=False` 范围内唯一。

#### Scenario: 同 provider 下 model_code 不可重复
- **WHEN** 创建 `provider_code="deepseek", model_code="deepseek-v4-flash"` 时已存在同名未删记录
- **THEN** 抛出 `BusinessException(code=400, message="该模型代码已存在")`

### Requirement: AI 模型配置 CRUD 接口
系统 SHALL 提供以下 REST 接口（统一前缀 `/ai-models`，挂载在 `/api/v1` 下）：

| 方法 | 路径 | operation_id | 说明 |
|---|---|---|---|
| POST | `/ai-models` | createAIModelConfig | 创建模型配置 |
| POST | `/ai-models/list` | getAIModelConfigList | 分页列表 |
| GET | `/ai-models/{id}` | getAIModelConfigById | 详情 |
| PATCH | `/ai-models/{id}` | updateAIModelConfig | 局部更新 |
| DELETE | `/ai-models/{id}` | deleteAIModelConfig | 软删除 |
| GET | `/ai-models/enabled` | getEnabledAIModels | 前端拉取可用列表（不含 api_key） |

所有接口响应统一走 `Execute.response()` + `ResponseModel[T]`。

#### Scenario: 创建模型配置
- **WHEN** POST `/ai-models`，body 含合法字段
- **THEN** 返回 `ResponseModel[AIModelConfigReo]`，`api_key` 字段返回脱敏值（如 `sk-****5678`），原始值落库

#### Scenario: 前端拉取可用模型列表
- **WHEN** GET `/ai-models/enabled`
- **THEN** 返回 `is_enabled=True AND is_deleted=False` 的记录列表，按 `sort_order` 升序、`created_at` 降序排列，**响应中不含 `api_key` 字段**（exclude=True）

#### Scenario: 默认模型互斥
- **WHEN** 更新某记录 `is_default=True`
- **THEN** 系统自动将其他记录的 `is_default` 置为 `False`（同一时刻全局仅一个默认模型）

#### Scenario: 软删除
- **WHEN** DELETE `/ai-models/{id}`
- **THEN** 仅置 `is_deleted=True`，不物理删除；后续查询与路由均不可见

### Requirement: 通用 AI 对话入口
系统 SHALL 提供以下通用入口（前缀 `/ai`）：

| 方法 | 路径 | operation_id | 说明 |
|---|---|---|
| GET | `/ai/health` | aiHealthCheck | 检查 AI 平台配置 |
| POST | `/ai/chat` | aiChat | 通用非流式对话 |
| POST | `/ai/chat/stream` | aiChatStream | 通用流式对话（SSE） |

`/ai/chat/stream` 入参（Form 表单，与现有 DeepSeek 对齐）：
- `model: str`（必填，model_code）
- `prompt: str`（必填）
- `system: Optional[str]`
- `thinking: str = "false"`
- `enable_search: bool = False`
- `files: Optional[List[UploadFile]]`

#### Scenario: 通用流式对话
- **WHEN** 前端 POST `/ai/chat/stream`，传 `model="deepseek-v4-flash"`、`thinking="true"`
- **THEN** 后端按 `model_code` 路由到 `DeepSeekProvider`，输出统一 SSE 事件流，首条为 `thinking` 事件

## MODIFIED Requirements

### Requirement: 路由注册
`app/api/v1/api.py` SHALL 新增对 `ai` 与 `ai_model_config` 两个 router 的挂载：
- `ai.router` → prefix=`/ai`, tags=`["AI"]`
- `ai_model_config.router` → prefix=`/ai-models`, tags=`["AI Model Config"]`

两个新路由默认不加 `get_current_user` 依赖（与现有 deepseek/ollama 路由保持一致），后续可在统一鉴权改造中补齐。

### Requirement: Alembic 模型注册
`alembic/env.py` SHALL 导入 `AIModelConfig` 模型，确保 `alembic revision --autogenerate` 能识别新表。

## REMOVED Requirements
无（本 spec 不移除任何现有能力，旧 DeepSeek/Ollama 路由保留向后兼容）。
