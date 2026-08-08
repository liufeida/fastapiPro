# 会话历史记录 - Product Requirement Document

## Overview
- **Summary**: 为 AI 对话平台增加会话（Conversation）和消息（Message）持久化能力，支持多轮对话上下文、会话管理（列表/详情/删除/重命名）、以及面向未来 RAG/Skill/Agent 扩展的消息附件系统。
- **Purpose**: 当前 `/chat/stream` 接口每次调用独立，无会话关联，无法进行多轮对话、无法回顾历史。需要建立面向用户的会话管理层，与现有的底层调用日志（`ai_chat_log`）并行，前者给前端看，后者做审计。
- **Target Users**: 前端开发者（消费 REST API）、终端用户（查看/管理自己的 AI 对话历史）。

## Goals
- 建立 `chat_conversation`（会话）和 `chat_message`（消息）两张核心表，与现有 `ai_chat_log` 并行不耦合
- 支持会话的完整生命周期：创建、查询、重命名、软删
- 每次 AI 对话流式结束后，自动持久化 user 消息 + assistant 消息（含 thinking 内容分离存储）
- 支持多轮对话上下文组装：dispatcher 根据 conversation_id 自动查历史消息拼 messages 数组，thinking_content 不参与模型上下文
- Provider 层接口升级：`chat` / `chat_stream` / `chat_stream_with_tools` 新增可选 `messages` 参数，保持向后兼容（未传时走原 `prompt + system` 路径）
- 消息附件系统预留：`chat_message_attachment` 关联表，与现有 `file` 表解耦独立引用，为未来图片/音频/文档多模态输入输出打基础
- 代码规范：每个 Service 方法写明作用注释，Repository 层风格与现有 `ai_chat_log_repository` 保持一致

## Non-Goals (Out of Scope)
- 不做前端 UI（聊天气泡界面、会话侧边栏等）
- 不做 Redis 缓存热点会话（可后期加，初期直接查 DB 够用）
- 不做消息编辑 / 重新生成（属于方案 C，后续加）
- 不做会话自动摘要压缩 / token 裁剪窗口管理（属于方案 C）
- 不做 AI 图片生成（本次只预留附件存储结构，不实现图片生成 SSE 事件）
- 不做 WebSocket 实时通知（会话变更后前端自己轮询）
- 不修改 `/files` 上传接口（附件关联走已有的 file 表）

## Background & Context
- 项目使用 FastAPI + SQLModel + PostgreSQL + asyncpg
- 现有模型层：`SQLModel`（带 `ConfigDict(from_attributes=True)` 返回模型风格）
- 现有仓储层：异步风格，参照 `ai_chat_log_repository`
- 现有服务层：`AIChatLogger` 做流式日志旁路收集 + `log_queue` 异步批量写库
- 现有 Provider 接口：`chat(config, prompt, system, thinking)` 和 `chat_stream_with_tools(config, prompt, system, thinking, enable_search, file_context)` — 都是单轮单 prompt 设计
- 现有 SSE 链路：`_event_generator()` 在路由层收集 thinking_parts / content_parts，流结束时拼完整字符串发 content_end / thinking_end 事件
- Provider 路径：每个 Provider 内部 `_build_messages(prompt, system, file_context)` 组装 `[{"role": "system", ...}, {"role": "user", ...}]`，传给 LangChain 或原生 httpx

## Functional Requirements
- **FR-1**: 创建会话 `POST /api/v1/conversations`：返回新创建的 conversation（含自动生成的 id），可选传入 user_id、title、model_code
- **FR-2**: 会话列表 `GET /api/v1/conversations`：按 user_id 分页查询，支持按标题关键词搜索，按 updated_at 倒序
- **FR-3**: 会话详情 `GET /api/v1/conversations/{conv_id}`：返回会话元数据 + 关联的全部消息列表（按创建时间升序）
- **FR-4**: 会话重命名 `PATCH /api/v1/conversations/{conv_id}`：更新 title 字段
- **FR-5**: 会话删除 `DELETE /api/v1/conversations/{conv_id}`：软删（标记 is_deleted=true），关联消息不级联物理删除
- **FR-6**: `/chat` 和 `/chat/stream` 新增可选 `conversation_id` 参数：传了则关联到已有会话，没传则每次自动创建新会话
- **FR-7**: 流式对话正常结束（stop_reason="stop"）后，自动持久化两条消息：一条 role=user、一条 role=assistant；thinking 内容写入 assistant 消息的 thinking_content 字段
- **FR-8**: 流式对话异常结束（stop_reason="error"）时，不持久化 assistant 消息（避免存一条空或错误回复）
- **FR-9**: dispatcher 根据 conversation_id 自动查询最近 N 条历史消息（默认全部，可加 token 裁剪），组装成 messages 数组传给 provider；thinking_content 不参与模型上下文
- **FR-10**: Provider 接口（AIProvider 基类 + 各 Provider 实现）新增可选 `messages: list[dict] | None` 参数，优先使用；未传时回退到原 `_build_messages(prompt, system, file_context)` 逻辑
- **FR-11**: 消息附件系统：`chat_message_attachment` 关联表，可关联 0~N 个 file 表记录，支持 image/document/audio 等 type 分类
- **FR-12**: 多轮上下文组装逻辑：system prompt + 历史消息（只取 content，跳过 thinking_content）+ 当前用户消息；附件消息拼 content 数组（text + image_url）
- **FR-13**: 会话自动生成标题：首次对话成功后，取首条用户消息的前 30 字符作为默认 title；用户可手动 PATCH 修改
- **FR-14**: 所有新模型、service、repository 代码风格与项目现有代码保持一致，每个公开方法写明中文 docstring

## Non-Functional Requirements
- **NFR-1**: 消息持久化必须在 SSE 流结束事件（end + stop_reason="stop"）之后执行，异步非阻塞，不影响前端流的完整消费
- **NFR-2**: 多轮上下文查询 + 组装的耗时应 < 100ms（单次 DB 查询 + 内存拼接）
- **NFR-3**: Provider 接口升级必须完全向后兼容：现有调用 `chat(prompt="xxx", system="xxx")` 不传 messages 的代码路径行为不变
- **NFR-4**: 所有新表必须通过 alembic migration 管理，不依赖 lifespan 的 create_all
- **NFR-5**: 会话历史查询接口必须返回结构化 Pydantic Reo 模型，不能直接暴露 ORM 字段

## Constraints
- **Technical**: 必须使用项目已有的 SQLModel + asyncpg 技术栈，不能引入新 ORM
- **Technical**: Provider 基类签名变更必须同步更新所有 Provider 实现（deepseek_provider, qwen_provider，及未来新增）
- **Technical**: SQLModel 的 `field_validator` 处理空字符串 → None 的模式必须复用现有风格
- **Business**: 不破坏现有 `/chat` 和 `/chat/stream` 的请求/响应格式，所有新增参数均为可选

## Assumptions
- 暂时不考虑"一条消息里既有文字又有图片"的多模态输入的真实模型调用（FR-11 只建存储结构），真正的多模态模型调用可后续加
- user_id 暂时可空（兼容匿名对话），后续 auth 中间件完善后再强绑
- 会话自动标题取前 30 字符够用，后续可接轻量 LLM 自动摘要
- alembic 已初始化过，migration 走 `alembic revision --autogenerate -m "xxx"`

## Acceptance Criteria

### AC-1: 数据库迁移成功
- **Given**: alembic 已配置，target_metadata 包含新模型
- **When**: 执行 `alembic upgrade head`
- **Then**: chat_conversation、chat_message、chat_message_attachment 三张表创建成功，服务重启不报错
- **Verification**: `programmatic`

### AC-2: 创建会话接口可用
- **Given**: POST `/api/v1/conversations` 传空 body 或带 title
- **When**: 发起请求
- **Then**: 返回 200，body 含新建 conversation 完整信息（id, title, model_code, created_at 等）
- **Verification**: `programmatic`

### AC-3: 会话列表分页查询
- **Given**: 数据库中有多条会话记录
- **When**: GET `/api/v1/conversations?page=1&pageSize=10`
- **Then**: 返回 records（数组）、total、page、pageSize、pages 五个字段，按 updated_at 倒序
- **Verification**: `programmatic`

### AC-4: 会话详情含消息列表
- **Given**: 某会话有多轮对话
- **When**: GET `/api/v1/conversations/{conv_id}`
- **Then**: 返回会话元数据 + messages 数组，按 created_at 升序，每条消息含 role、content、thinking_content（可空）
- **Verification**: `programmatic`

### AC-5: 重命名会话
- **Given**: 存在 conversation id=xxx
- **When**: PATCH `/api/v1/conversations/{conv_id}` body `{"title": "新标题"}`
- **Then**: 返回 200，title 更新成功
- **Verification**: `programmatic`

### AC-6: 删除会话（软删）
- **Given**: 存在 conversation id=xxx
- **When**: DELETE `/api/v1/conversations/{conv_id}`
- **Then**: 返回 200，查询列表时该会话不再出现（is_deleted=true），详情接口返回 404
- **Verification**: `programmatic`

### AC-7: chat_stream 自动创建会话并持久化消息
- **Given**: POST `/api/v1/ai/chat/stream` 不传 conversation_id
- **When**: 流正常结束（stop_reason="stop"）
- **Then**: 数据库中自动创建一条 conversation + 两条 message（role=user + role=assistant）
- **Verification**: `programmatic`

### AC-8: chat_stream 关联已有会话并持久化
- **Given**: POST `/api/v1/ai/chat/stream` 传 conversation_id=xxx
- **When**: 流正常结束
- **Then**: 向已有会话追加两条新 message，conversation 的 updated_at 更新
- **Verification**: `programmatic`

### AC-9: 流异常结束不持久化 assistant 消息
- **Given**: chat_stream 中途超时或抛异常
- **When**: stop_reason="error"
- **Then**: 只可能有 user 消息（如果提前写了），assistant 消息不写入
- **Verification**: `programmatic`

### AC-10: 多轮上下文组装只取 content
- **Given**: 某会话有多轮历史（含 thinking_content）
- **When**: 发起新一轮对话
- **Then**: 传给 Provider 的 messages 数组中，历史消息只含 role + content，thinking_content 不出现
- **Verification**: `programmatic`

### AC-11: Provider 接口向后兼容
- **Given**: Provider 的 chat / chat_stream / chat_stream_with_tools 方法签名新增 messages 参数
- **When**: 现有调用不传 messages
- **Then**: 行为与之前完全一致（走 _build_messages 路径）
- **Verification**: `programmatic`

### AC-12: 多 Provider 都支持 messages 参数
- **Given**: 至少 deepseek_provider 和 qwen_provider 都升级了接口
- **When**: 调用方传 messages=[{"role":"system",...},{"role":"user",...}]
- **Then**: 两个 Provider 都优先使用传入的 messages，不再调用 _build_messages
- **Verification**: `programmatic`

### AC-13: 会话列表关键词搜索
- **Given**: 有标题为"Python排序"和"Go协程"的两条会话
- **When**: GET `/api/v1/conversations?keyword=排序`
- **Then**: 只返回匹配的那条
- **Verification**: `programmatic`

### AC-14: 代码注释规范
- **Given**: 新增的 service / repository 层公开方法
- **When**: 代码评审
- **Then**: 每个公开方法有中文 docstring 说明作用、参数、返回值
- **Verification**: `human-judgment`
- **Notes**: 参照现有 `ai_chat_log_repository` 和 `AIChatLogger` 的注释风格

### AC-15: 代码风格一致
- **Given**: 新增所有代码
- **When**: 与项目现有文件对比
- **Then**: SQLModel 模型风格（ConfigDict、optional uuid、DateTime timezone）、Repository 异步风格、Service 分层均与现有一致
- **Verification**: `human-judgment`

## Open Questions
- [ ] 多轮上下文的最大消息条数或 token 上限暂不实现（属于方案 C），默认全部加载；但是否需要预留常量配置位？（倾向：先全部加载，留 TODO 注释标记）
- [ ] 是否需要在 chat_stream 的 SSE 流中新增一个 `conversation_id` 字段让前端知道这次请求关联到哪个会话？（倾向：在 start 事件里加 conversation_id 字段）
- [ ] 消息的 created_at 是路由层生成还是数据库默认？（倾向：数据库 DateTime timezone 默认值，和现有 User 表一致）
- [ ] 会话 user_id 是否强制？（倾向：可空，兼容匿名；auth 完善后再加约束）
