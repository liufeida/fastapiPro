# 会话历史记录 - Verification Checklist

## 数据库 + 迁移
- [ ] alembic migration 文件生成，含 chat_conversation / chat_message / chat_message_attachment 三张表
- [ ] `alembic upgrade head` 执行成功，PostgreSQL 中三张表存在
- [ ] `alembic downgrade -1` 能正确回退新表
- [ ] 服务 lifespan 启动正常（SQLModel metadata 不重复建表报错）

## 数据模型
- [ ] chat_conversation 表：id (uuid hex PK), user_id, title, model_code, is_deleted (bool default false), created_at, updated_at — 全部字段与 spec 一致
- [ ] chat_message 表：id, conversation_id (FK), role, content (Text nullable), thinking_content (Text nullable), tokens_input, tokens_output, created_at
- [ ] chat_message_attachment 表：id, message_id (FK), file_id (FK), url, filename, content_type, type, created_at
- [ ] 三张表的 Pydantic Reo / Create 模型都有 ConfigDict(from_attributes=True)

## Repository 层
- [ ] 每个 repository 有单例导出（`xxx_repository = XxxRepository()`）
- [ ] 所有方法接受 AsyncSession 作为第一个参数
- [ ] 每个公开方法有中文 docstring（作用 + 参数 + 返回值）
- [ ] ChatConversationRepository.list_paginated 支持 user_id / keyword / is_deleted 过滤，按 updated_at desc
- [ ] ChatMessageRepository.create_batch 接收 list[dict] 批量插入
- [ ] ChatMessageRepository.list_by_conversation 按 created_at asc 返回

## Service 层
- [ ] ChatConversationService.ensure_conversation: 传 conversation_id → 返回存在的；不传或找不到 → 创建新的并返回 id
- [ ] ChatConversationService.record_message_pair: 事务内批量写 user + assistant 两条 message + update conversation.updated_at
- [ ] chat_context.build_messages_for_provider: 查历史 → 拼 system + history_messages + user 的完整 list[dict]
- [ ] build_messages_for_provider 输出的每条 dict 只有 role 和 content，绝不出现 thinking_content
- [ ] build_messages_for_provider 中 file_context 拼到当前 user prompt 里（沿用现有格式 `【文件上下文】\n...\n\n【用户问题】\n...`）

## Provider 接口升级
- [ ] AIProvider 基类 chat / chat_stream / chat_stream_with_tools 签名新增 messages: Optional[list[dict]] = None
- [ ] DeepSeekProvider 三个方法：messages is not None → 直接用；否则 _build_messages 回退
- [ ] QwenProvider 三个方法：同上
- [ ] 不传 messages 的现有调用行为完全不变（回归验证：不传 conversation_id 时模型正常响应）
- [ ] messages 路径时，provider 内部的 _to_langchain_messages / _stream_raw 都接收 messages 并使用

## Dispatcher 集成
- [ ] AIDispatcher.chat / chat_stream_with_tools 新增 conversation_id / user_id 可选参数
- [ ] conversation_id 存在 → 调用 build_messages_for_provider → provider(..., messages=messages)
- [ ] conversation_id 不存在 → 走原 prompt + system 路径，行为不变
- [ ] history messages 不包含 thinking_content（已由 context assembler 保证）

## 路由层
- [ ] chat_stream Form 参数新增 conversation_id: Optional[str] = Form(None)
- [ ] ChatRequest 新增 conversation_id / user_id Optional 字段
- [ ] chat_stream 入口调用 ensure_conversation → 拿到 conversation_id 传给 dispatcher
- [ ] start SSE 事件 payload 包含 conversation_id 字段（前端可感知）
- [ ] chat_stream 正常结束（stop_reason="stop"）→ 调 record_message_pair 持久化两条消息
- [ ] chat_stream 异常结束（stop_reason="error"）→ 不持久化 assistant 消息
- [ ] 非流式 chat 接口同理：正常返回后持久化；抛异常不持久化

## 会话管理 REST API
- [ ] POST /api/v1/conversations → 200，返回新建 conversation
- [ ] GET /api/v1/conversations → 200，返回 {records, total, page, pageSize, pages}
- [ ] GET /api/v1/conversations?keyword=xxx → 过滤匹配标题
- [ ] GET /api/v1/conversations/{conv_id} → 200，返回会话元数据 + messages 数组
- [ ] GET /api/v1/conversations/{conv_id} 不存在 → 404
- [ ] PATCH /api/v1/conversations/{conv_id} body {"title":"xxx"} → 200，title 更新
- [ ] DELETE /api/v1/conversations/{conv_id} → 200，is_deleted=true
- [ ] 软删后列表不再返回、详情接口返回 404

## 端到端联调
- [ ] 完整 happy path：POST conv → chat_stream → GET detail（验证有两条 message）→ 第二条 chat_stream（带 conversation_id）→ GET detail（验证有四条 message）
- [ ] 多轮上下文生效：第二轮对话能引用第一轮的内容（模型输出"你刚才问的..."表明历史已注入）
- [ ] thinking 不进入上下文：第二轮 messages 中不含 thinking_content（查 DB 验证）
- [ ] 错误处理：强制注入超时 → DB 中不应有不完整的 assistant message
- [ ] 多 Provider 验证：deepseek + qwen 都能通过 messages 参数正常响应

## 代码规范
- [ ] 所有新增公开方法有中文 docstring
- [ ] SQLModel 模型风格与现有 ai_chat_log / users 一致
- [ ] 仓储层 async session 注入风格一致
- [ ] 路由层用 Execute.response 包裹返回值
- [ ] 无未使用的 import / 变量
- [ ] 无 TODO/FIXME/HACK 遗留（除预留的多模态扩展 TODO）

## 开发文档
- [ ] docs/ai-architecture/03-chat-history-260808.md 存在
- [ ] 文档包含：架构图（Mermaid）、表结构、Provider 接口说明、Dispatcher 流程、SSE 持久化时机、API 列表 + 请求/响应示例、多轮时序图、ai_chat_log 关系图、RAG/Skill/Agent 扩展预留
- [ ] 文档风格与 02-sse-streaming.md 一致（代码引用带行号、Mermaid 图、ASCII 链路图）
