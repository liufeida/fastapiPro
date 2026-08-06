# Checklist

## 数据模型
- [x] `app/models/ai_model_config.py` 已创建，字段与 spec.md 表结构完全一致
- [x] `AIModelConfig` 表模型包含 `id`(uuid hex PK)、`created_at`、`updated_at`、`is_deleted`
- [x] `AIModelConfigReo` 配置 `model_config = ConfigDict(from_attributes=True)`
- [x] `AIModelConfigUpdate` 所有字段 Optional，空字符串归一化为 None
- [x] `QueryRequest` 支持 `keyword` / `provider_code` / `is_enabled` 过滤
- [x] `alembic/env.py` 已导入 `AIModelConfig`
- [x] 迁移文件已生成，建表语句完整，含种子数据（DeepSeek + Ollama 各一条）

## Provider 抽象层
- [x] `app/services/ai/base.py` 定义了 `AIProvider` 抽象基类与 3 个抽象方法
- [x] `app/services/ai/registry.py` 实现 `ProviderRegistry`，单例 `provider_registry`
- [x] `app/services/ai/sse.py` 提供 `build_sse(event, data)`，data 强制 JSON、`ensure_ascii=False`
- [x] 未注册 provider 查询时抛 `BusinessException(code=500)`

## DeepSeek Provider
- [x] `DeepSeekProvider` 实现 `AIProvider` 全部 3 个方法
- [x] `thinking=false` 走 LangChain `ChatDeepSeek`，配置从 `AIModelConfig` 读取
- [x] `thinking=true` 走原生 httpx，从 `delta.reasoning_content` 提取思考内容（硬约束）
- [x] `chat_stream` 与 `chat_stream_with_tools` 均支持 thinking 提取
- [x] 模块加载时注册到 `provider_registry`（key="deepseek"）

## Ollama Provider
- [x] `OllamaProvider` 实现 `AIProvider` 全部 3 个方法
- [x] 配置从 `AIModelConfig.base_url` 与 `extra_config` 读取，不再硬编码
- [x] 流式输出 data 为 JSON（`{"content": "..."}`），与 DeepSeek 格式一致
- [x] 模块加载时注册到 `provider_registry`（key="ollama"）

## 调度器
- [x] `ai_dispatcher.resolve` 校验 `is_enabled` 与 `is_deleted`
- [x] `ai_dispatcher.check_capability` 校验 thinking/tools 能力，不匹配抛 400
- [x] `ai_dispatcher` 单例导出
- [x] provider 注册副作用在应用启动时执行（导入即注册）

## CRUD Repository
- [x] `AIModelConfigRepository` 实现 get_by_id / get_by_model_code / exists_by_provider_and_code / create / update / soft_delete / list_enabled / list_paginated / count / clear_other_defaults
- [x] 所有查询过滤 `is_deleted=False`
- [x] 单例 `ai_model_config_repository` 导出

## CRUD Service
- [x] `AIModelConfigServices.create` 做唯一性校验 + 默认互斥
- [x] `AIModelConfigServices.update` 用 `exclude_unset`、改 code 时重新唯一性校验、改 is_default 时互斥
- [x] `AIModelConfigServices.list_enabled` 响应中 exclude `api_key`
- [x] 所有返回 `AIModelConfigReo` 的方法对 `api_key` 做脱敏（`mask_api_key`）
- [x] 单例 `ai_model_config_services` 导出

## CRUD 路由
- [x] 6 个接口全部挂载，operation_id 与 spec 一致
- [x] 所有接口用 `SessionDeep` 依赖注入
- [x] 所有响应走 `Execute.response()` + `ResponseModel[T]`
- [x] `/ai-models/enabled` 响应不含 `api_key`

## 通用 AI 路由
- [x] `/ai/health` 返回 provider 列表 + 启用模型数
- [x] `/ai/chat` 接收 JSON body，调用 dispatcher
- [x] `/ai/chat/stream` Form 入参与现有 DeepSeek 对齐（含 files）
- [x] 流式入口用 `build_sse` 输出统一事件（thinking/content/tool/tool_result/Done/error）
- [x] 入口前调用 `check_capability` 做能力校验
- [x] 错误兜底发 `error` 事件，不发原始堆栈

## 路由挂载
- [x] `app/api/v1/api.py` 挂载 `ai.router`（prefix=/ai, tags=["AI"]）
- [x] `app/api/v1/api.py` 挂载 `ai_model_config.router`（prefix=/ai-models, tags=["AI Model Config"]）
- [x] 两个新路由未加 `get_current_user` 依赖

## 向后兼容
- [x] `app/api/v1/deepseek.py` 与 `app/services/deepseek.py` 未被破坏性修改
- [x] `app/api/v1/ollama.py` 未被破坏性修改
- [x] 旧接口 `/deepseek/chat/stream` 仍可正常调用

## 验证
- [x] 服务启动无导入错误
- [x] `/api/docs` 展示 `AI` 与 `AI Model Config` 两组接口
- [ ] `alembic upgrade head` 成功建表且种子数据写入
- [ ] `GET /ai-models/enabled` 返回列表且不含 `api_key`
- [ ] `POST /ai/chat/stream`（deepseek + thinking=true）输出含 thinking 事件的 SSE 流
- [ ] `POST /ai/chat/stream`（不支持思考的模型 + thinking=true）返回 400
- [ ] `POST /ai-models` 创建重复 model_code 返回 400
