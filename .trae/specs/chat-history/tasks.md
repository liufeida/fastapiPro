# 会话历史记录 - The Implementation Plan

## [ ] Task 1: 数据模型 + Alembic Migration
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 新建 `app/models/chat_conversation.py`：chat_conversation 表（id, user_id, title, model_code, is_deleted, created_at, updated_at）+ Pydantic Reo/Create/Update 模型
  - 新建 `app/models/chat_message.py`：chat_message 表（id, conversation_id, role, content, thinking_content, tokens_input, tokens_output, created_at）+ Reo 模型
  - 新建 `app/models/chat_message_attachment.py`：chat_message_attachment 表（id, message_id, file_id, url, filename, content_type, type, created_at）
  - 更新 `alembic/env.py` 导入新模型
  - 执行 `alembic revision --autogenerate -m "add_chat_history_tables"` 生成迁移文件并 review
  - 执行 `alembic upgrade head` 验证建表成功
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-1.1: `alembic upgrade head` 执行成功，无报错
  - `programmatic` TR-1.2: 服务 lifespan 启动正常（create_all 不冲突）
  - `programmatic` TR-1.3: `alembic downgrade -1` 能回退新表
- **Notes**: SQLModel 风格完全参照现有 `ai_chat_log.py` 和 `users.py`，uuid hex primary_key，DateTime timezone default_factory

## [ ] Task 2: Repository 层（Conversation + Message + Attachment）
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 新建 `app/repository/chat_conversation.py`：ChatConversationRepository，方法含 create、get_by_id、list_paginated（支持 user_id + keyword 过滤 + updated_at desc）、soft_delete、rename、touch_updated_at
  - 新建 `app/repository/chat_message.py`：ChatMessageRepository，方法含 create_batch（一条 user + 一条 assistant 批量）、list_by_conversation（created_at asc）
  - 新建 `app/repository/chat_message_attachment.py`：ChatMessageAttachmentRepository，方法含 create、list_by_message
  - 所有仓储类风格与 `ai_chat_log_repository` 对齐（单例导出、async session 参数、方法 docstring）
- **Acceptance Criteria Addressed**: AC-15
- **Test Requirements**:
  - `programmatic` TR-2.1: 每个 repository 类可实例化，方法签名正确
  - `human-judgement` TR-2.2: 代码风格（async session 注入、filter 构建、scalar_one_or_none 返回）与 ai_chat_log_repository 一致
  - `human-judgement` TR-2.3: 每个公开方法有中文 docstring

## [ ] Task 3: Service 层（Conversation Service + Context Assembler）
- **Priority**: high
- **Depends On**: Task 2
- **Description**:
  - 新建 `app/services/chat_conversation.py`：ChatConversationService，封装会话完整业务逻辑
    - `create_conversation(session, user_id, model_code, initial_title)` → 创建会话
    - `ensure_conversation(session, conversation_id, user_id, model_code)` → 有则返回、无则创建
    - `soft_delete(session, conversation_id)` → 软删
    - `rename(session, conversation_id, title)` → 重命名
    - `record_message_pair(session, conversation_id, user_content, assistant_content, thinking_content, tokens_input, tokens_output)` → 批量写 user + assistant 两条消息，同时更新 conversation.updated_at
  - 新建 `app/services/chat_context.py`：build_messages_for_provider(session, conversation_id, system_prompt, current_user_prompt, file_context)
    - 查 chat_message 最近全部历史（role != assistant 也包含，但只取 content）
    - 组装 messages 数组：`[{"role": "system", "content": system_prompt}] + history_messages + [{"role": "user", "content": final_prompt}]`
    - thinking_content 绝不传入
    - file_context 拼到当前 user prompt 里（沿用现有 `_build_messages` 逻辑）
    - attachment 关联查询暂只取 file_url 列表，预留 type 判断注释（TODO: 多模态真正拼 content 数组）
- **Acceptance Criteria Addressed**: AC-10, AC-14
- **Test Requirements**:
  - `programmatic` TR-3.1: build_messages_for_provider 返回 list[dict]，每条只有 role + content key
  - `programmatic` TR-3.2: 输入含 thinking_content 的历史消息时，输出 messages 数组中不出现
  - `human-judgement` TR-3.3: 所有公开方法有中文 docstring，说明作用、参数、返回值
- **Notes**: chat_context.py 是独立的纯函数风格 service，不依赖全局状态，方便单元测试

## [ ] Task 4: Provider 接口升级（基类 + 全部实现）
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - 修改 `app/services/ai/base.py`：AIProvider 抽象基类的 chat / chat_stream / chat_stream_with_tools 三个方法签名新增 `messages: Optional[list[dict]] = None` 参数（放在 prompt 之后、system 之前或 system 之后，确保不破坏现有位置调用）
  - 修改 `app/services/ai/deepseek_provider.py`：三个方法内部优先判断 `messages is not None` → 直接用传入的 messages；否则走原 `_build_messages(prompt, system, file_context)` 路径
  - 修改 `app/services/ai/qwen_provider.py`：同上逻辑同步更新
  - Provider 基类 docstring 更新：说明 messages 参数用途和优先级
- **Acceptance Criteria Addressed**: AC-11, AC-12
- **Test Requirements**:
  - `programmatic` TR-4.1: Provider 实例调用 chat(prompt="xxx", system="xxx") 不传 messages 行为不变
  - `programmatic` TR-4.2: Provider 实例调用 chat(messages=[{"role":"system",...},{"role":"user",...}]) 时 messages 直接进入模型请求体
  - `programmatic` TR-4.3: chat_stream 和 chat_stream_with_tools 同理两条路径验证
- **Notes**: 这是对所有 Provider 的破坏性变更点，但保持了向后兼容。所有新增 Provider 必须继承新基类。

## [ ] Task 5: Dispatcher 集成（上下文组装 + messages 传递）
- **Priority**: high
- **Depends On**: Task 3, Task 4
- **Description**:
  - 修改 `app/services/ai/dispatcher.py`：AIDispatcher.chat 和 chat_stream_with_tools 方法新增 conversation_id、user_id 可选参数
  - 当 conversation_id 存在时，调用 `chat_context.build_messages_for_provider()` 拿到完整 messages 数组，传给 provider.chat(..., messages=messages) 代替原 prompt + system
  - 当 conversation_id 不存在时，保持原行为（只传 prompt + system）
  - 文件上下文 file_context 的拼接仍沿用 `_build_identity_system` 中 system prompt 构建逻辑，context assembler 负责把 file_context 拼到 user prompt 里
- **Acceptance Criteria Addressed**: AC-10, AC-11, AC-12
- **Test Requirements**:
  - `programmatic` TR-5.1: 无 conversation_id 的调用与之前行为完全一致
  - `programmatic` TR-5.2: 有 conversation_id 时 messages 数组含历史对话
  - `programmatic` TR-5.3: 历史消息中的 thinking_content 不进入 messages 数组

## [ ] Task 6: 路由层集成（chat / chat_stream + SSE 流后持久化）
- **Priority**: high
- **Depends On**: Task 5
- **Description**:
  - 修改 `app/api/v1/ai.py`：
    - ChatRequest 新增 conversation_id: Optional[str] = None、user_id: Optional[str] = None
    - chat_stream 路由的 Form 参数新增 conversation_id: Optional[str] = Form(None)
    - chat_stream 的 start SSE 事件新增 conversation_id 字段（让前端知道这次请求关联到哪个会话）
    - 在 chat_stream 的 `_event_generator()` 正常结束路径中，stop_reason="stop" 时调用 `chat_conversation_service.record_message_pair()` 持久化 user + assistant 两条消息
    - 在 chat_stream 入口处（流开始前）调用 `ensure_conversation` 创建/获取 conversation_id 并传给 dispatcher
    - 同时修改 `ChatRequest` 对应的 `chat` 非流式接口，加上同样的 conversation_id 持久化逻辑
- **Acceptance Criteria Addressed**: AC-7, AC-8, AC-9
- **Test Requirements**:
  - `programmatic` TR-6.1: chat_stream 不传 conversation_id → DB 新增 1 conversation + 2 messages
  - `programmatic` TR-6.2: chat_stream 传 conversation_id → DB 追加 2 messages 到已有 conversation
  - `programmatic` TR-6.3: chat_stream 中途 timeout / error → assistant message 不写入
  - `programmatic` TR-6.4: start SSE 事件 payload 包含 conversation_id
- **Notes**: SSE 流持久化的时机非常关键——必须在 stop_reason="stop" 分支内，基于已收集好的 content_parts 和 thinking_parts。stop_reason="error" 分支跳过写 assistant 消息。

## [ ] Task 7: 会话管理 REST API（路由 + 注册）
- **Priority**: high
- **Depends On**: Task 2, Task 3
- **Description**:
  - 新建 `app/api/v1/chat_conversations.py`：路由文件
    - POST `/conversations` → create_conversation
    - GET `/conversations` → list_conversations（分页 + keyword + user_id 过滤）
    - GET `/conversations/{conv_id}` → get_conversation_detail（含 messages 列表）
    - PATCH `/conversations/{conv_id}` → rename_conversation
    - DELETE `/conversations/{conv_id}` → soft_delete_conversation
  - 修改 `app/api/v1/api.py`：include_router(chat_conversations.router, prefix="/conversations")
  - 所有接口用 Execute.response 包裹返回（和现有 users / prompts 接口风格一致）
- **Acceptance Criteria Addressed**: AC-2, AC-3, AC-4, AC-5, AC-6, AC-13
- **Test Requirements**:
  - `programmatic` TR-7.1: 五个 HTTP 端点返回 200
  - `programmatic` TR-7.2: 列表接口支持 page/pageSize/keyword 参数
  - `programmatic` TR-7.3: 软删后列表不再返回、详情返回 404
  - `human-judgement` TR-7.4: 代码风格与现有路由文件（users.py、prompts.py）一致

## [ ] Task 8: 联调测试 + Bug 修复
- **Priority**: medium
- **Depends On**: Task 1-7
- **Description**:
  - 运行 `alembic upgrade head` 验证所有表建好
  - 启动服务，用 HTTPie / curl / Trae API Client 逐一跑通：
    - 创建会话 → 调用 chat_stream → 查会话详情（验证消息已持久化）→ 再调 chat_stream（带 conversation_id）→ 查详情（验证多轮历史）
    - 重命名 → 软删 → 列表过滤
    - 中途断流/超时场景：发送请求后立即断网，检查 DB 不应有不完整记录
  - 跑通多 Provider（deepseek + qwen），验证 messages 参数兼容
  - 修复联调中发现的 Bug
- **Acceptance Criteria Addressed**: AC-1 ~ AC-13 全部
- **Test Requirements**:
  - `programmatic` TR-8.1: 完整 happy path：POST conv → chat_stream → GET detail → 第二条 chat_stream → GET detail（两轮都在）
  - `programmatic` TR-8.2: 错误 path：强制注入超时 → DB 中只有 user message，无 assistant
  - `programmatic` TR-8.3: 代码修改后启动服务无 startup 错误
- **Notes**: 这步是所有 Task 的汇总验证，发现问题要回修前面 Task 的代码

## [ ] Task 9: 编写开发文档 docs/ai-architecture/03-chat-history-260808.md
- **Priority**: medium
- **Depends On**: Task 8
- **Description**:
  - 文档内容：架构设计图（Mermaid）、数据表结构说明、Provider 接口升级说明、Dispatcher 上下文组装流程、SSE 流后持久化时机说明、API 接口列表（请求/响应示例）、多轮对话完整链路时序图、与 ai_chat_log 的关系、未来扩展（RAG/Skill/Agent 预留位）
  - 文件名 `03-chat-history-260808.md`（docs/ai-architecture/ 目录下，延续现有编号风格 01/02）
- **Acceptance Criteria Addressed**: AC-14
- **Test Requirements**:
  - `human-judgement` TR-9.1: 文档结构清晰，所有代码路径与项目实际一致
  - `human-judgement` TR-9.2: 包含 Mermaid 时序图展示多轮对话完整链路
- **Notes**: 参照现有 02-sse-streaming.md 的风格，内容要能指导后续 RAG/Skill/Agent 开发
