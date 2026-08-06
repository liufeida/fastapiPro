# Prompt 工程管理 + 接口日志 - 实施计划

## [x] Task 1: Prompt 模块 - Model / Repository / Service / Cache
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 在 `app/models/prompt.py` 中定义 `SystemPrompt` SQLModel（Base + Create + Update + Reo），复用现有的 `PageParams`、`PageResult` 通用结构
  - 在 `app/repository/prompt.py` 中实现 `PromptRepository`（get_by_id / get_by_prompt_code / get_enabled_by_model / get_global_default / create / update / soft_delete / list_paginated / count / clear_other_defaults 单例导出）
  - 在 `app/services/prompt.py` 中实现 `PromptServices`（CRUD 校验 + 默认标记互斥 + 单例导出）
  - 在 `app/services/prompt_cache.py` 中实现 `PromptCache` 类（内存 dict 缓存，key 为 model_code，value 为 SystemPrompt；提供 `warm_up(session)` 启动加载、`refresh(session)` 增删改后刷新、`resolve(model_code)` 查询匹配）
- **Acceptance Criteria Addressed**: AC-1, AC-3
- **Test Requirements**:
  - `programmatic` TR-1.1: PromptModel 能正确从 dict 创建、序列化为 dict，含软删除标记
  - `programmatic` TR-1.2: Repository 的 get_enabled_by_model 能按 model_code 精确匹配 + 全局 default 兜底
  - `programmatic` TR-1.3: Service 创建时 prompt_code 唯一校验、is_default 互斥生效
  - `programmatic` TR-1.4: PromptCache.warm_up 能从 DB 加载所有未删除且启用的 Prompt
  - `programmatic` TR-1.5: PromptCache.resolve(model_code) 在 model_code 精确匹配时返回对应 Prompt，否则返回全局默认
- **Notes**: 缓存 resolve 优先级为 **model_code 精确匹配** > **全局默认（model_code=null）** > **无 Prompt**（返回 None，由 Dispatcher 只用硬编码身份前缀）

---

## [x] Task 2: Prompt 模块 - API 路由注册 + Dispatcher 集成
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 在 `app/api/v1/prompts.py` 中实现路由（POST create / POST list / GET enabled / GET by_id / PATCH update / DELETE delete），复用 `ai_model_config.py` 的路由风格
  - 在 `app/api/v1/api.py` 中 include prompts_router
  - 改造 `dispatcher.py` 的 `_build_identity_system`：从硬编码改为先调 PromptCache.resolve(model_code) 拿到 DB Prompt，再叠加身份前缀（日期时间），最后拼接用户 system
  - 在 `main.py` 的 lifespan startup 里调用 `prompt_cache.warm_up(engine session)`
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3
- **Test Requirements**:
  - `programmatic` TR-2.1: POST /v1/prompts 创建后 PATCH 更新能正常修改 content
  - `programmatic` TR-2.2: Dispatcher 调 chat() 时，实际发给 LLM 的 system 包含 DB Prompt 内容（在 AI 日志中验证）
  - `programmatic` TR-2.3: 更新 Prompt 后（无需重启），下一次 AI 调用拿到新 content
  - `programmatic` TR-2.4: GET /v1/prompts/list 返回 PageResult，total/pages 正确

---

## [ ] Task 3: HTTP API 访问日志 - Model + Repository + Queue + Flush
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 在 `app/models/api_access_log.py` 中定义 `ApiAccessLog` SQLModel + QueryParams + PageResult
  - 在 `app/repository/api_access_log.py` 中实现 `ApiAccessLogRepository`（create_batch / list_paginated / count / delete_by_id，单例导出）
  - 在 `app/services/log_queue.py` 中实现 `LogQueue`：asyncio.Queue 封装 + enqueue() + flush_to_db(session) 批量写入 + 后台协程 start()/stop()（每 2s 或 > 50 条触发 flush）+ lifespan finally 中强制 flush
  - 批量写入用 `session.execute(insert(...).values(data_list))` 单条 SQL，避免 N 次 commit
- **Acceptance Criteria Addressed**: AC-4, AC-7
- **Test Requirements**:
  - `programmatic` TR-3.1: LogQueue.enqueue(data) 能正确放入队列且不阻塞
  - `programmatic` TR-3.2: flush_to_db 能批量写入多条记录，api_access_log 表中数据完整
  - `programmatic` TR-3.3: flush 后队列自动清空

---

## [x] Task 4: HTTP API 访问日志 - 中间件埋点
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - 改造 `app/core/middleware.py`，在 `register_middleware_handles` 中新增 `api_access_log_middleware`
  - 中间件职责：
    1. 生成 trace_id（uuid4），存入 contextvars.ContextVar
    2. 读取 request body（request.body() 只能读一次，要缓存下来再 replace 给后续 handler）
    3. 非流式响应：直接读取 response body 收集完整内容
    4. 流式响应：用 `StreamingResponse` 包装，在 async iterator 外层包一层收集 chunk，拼接后写入（或标注 is_streaming=true，response_body 存 `"(streaming)"` + 首 200 字符摘要）
    5. 捕获异常（try/except），记录 is_error + error_message，然后重新抛出
    6. 计算 duration_ms
    7. 调用 `log_queue.enqueue(api_access_log_dict)`
  - 脱敏：request_body 中匹配 `api_key`、`Authorization`、`token` 字段的值做 `***` 替换
  - 路由白名单：日志接口本身（`/v1/logs/*`）不记录，避免递归
- **Acceptance Criteria Addressed**: AC-4, AC-6, AC-8
- **Test Requirements**:
  - `programmatic` TR-4.1: 访问 `/api/v1/users` 等接口后 api_access_log 表新增记录
  - `programmatic` TR-4.2: trace_id 通过 contextvars 能传递到下游 AI 层
  - `programmatic` TR-4.3: 异常请求能记录 is_error=true + error_message 含异常类型
  - `programmatic` TR-4.4: 流式响应请求 is_streaming=true，response_body 包含 "(streaming)"
  - `programmatic` TR-4.5: 含 api_key 的请求体进入日志时已脱敏为 `***`

---

## [ ] Task 5: AI LLM 调用日志 - Model + Repository + Service + Dispatcher 埋点
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - 在 `app/models/ai_chat_log.py` 中定义 `AIChatLog` SQLModel + QueryParams + PageResult
  - 在 `app/repository/ai_chat_log.py` 中实现 `AIChatLogRepository`（create_batch / list_paginated / count / delete_by_id）
  - 在 `app/services/ai_logger.py` 中实现 `AIChatLogger`：
    - `from_context()` 从 contextvars 取 trace_id
    - `enqueue_log(log_dict)` 调用 LogQueue 入队（两种日志共用一个队列，加 type 字段）
    - `wrap_chat_stream_with_tools(dispatcher, ...)` 装饰器——包装 chat_stream_with_tools 的 async generator，收集 chunk 后 flush
  - 在 `dispatcher.py` 中改造 chat/chat_stream_with_tools：
    - chat() 完成后调用 `ai_logger.enqueue_log()`
    - chat_stream_with_tools 用 wrap 装饰器，记录完整 messages（含 system）、所有 chunk 拼接内容、thinking
    - 错误捕获后也要记录 is_error=true 的日志
  - **关键**：messages 内容在 dispatcher 层能拿到——因为 `system` 已经是合并后的完整 system，`prompt` 也在参数里。需要构造 `[{"role":"system","content":system}, {"role":"user","content":prompt}]` 作为 messages
  - trace_id 从 contextvars 读取（中间件已设置）
- **Acceptance Criteria Addressed**: AC-5, AC-6, AC-8
- **Test Requirements**:
  - `programmatic` TR-5.1: AI chat 调用完成后 ai_chat_log 表新增记录，含完整 messages
  - `programmatic` TR-5.2: chat_stream_with_tools 的日志 response_content 是所有 chunk 拼接后的完整内容
  - `programmatic` TR-5.3: 流式调用中 thinking_content 能被记录（如果 provider 有）
  - `programmatic` TR-5.4: 同一请求的 api_access_log 和 ai_chat_log trace_id 相同

---

## [x] Task 6: 日志 CRUD 查询 API
- **Priority**: medium
- **Depends On**: Task 3, Task 5
- **Description**:
  - 在 `app/api/v1/logs.py` 中实现路由：
    - `POST /v1/logs/api/list` — HTTP 访问日志分页列表
    - `GET /v1/logs/api/{id}` — HTTP 日志详情
    - `POST /v1/logs/ai/list` — AI 调用日志分页列表
    - `GET /v1/logs/ai/{id}` — AI 日志详情
    - `DELETE /v1/logs/api/{id}` — 物理删除单条
    - `DELETE /v1/logs/ai/{id}` — 物理删除单条
  - Repository 的 list_paginated + count 需支持：trace_id 精确、path/model_code 模糊、is_error 精确、时间范围（created_at >= X AND created_at <= Y）
  - 响应中的 request_body / response_body / messages 字段可能很大，前端分页列表可以做截断（比如返回前 1000 字符 + total_length 字段），详情接口返回完整
- **Acceptance Criteria Addressed**: AC-9
- **Test Requirements**:
  - `programmatic` TR-6.1: POST /v1/logs/api/list 返回 PageResult，筛选条件生效
  - `programmatic` TR-6.2: GET /v1/logs/api/{id} 返回完整数据（含大字段）
  - `programmatic` TR-6.3: 时间范围筛选正确

---

## [x] Task 7: Alembic Migration 生成 + 应用
- **Priority**: high
- **Depends On**: Task 1, Task 3, Task 5
- **Description**:
  - 生成 alembic migration：`alembic revision --autogenerate -m "add_prompt_and_logs_tables"`
  - 检查生成的 migration 内容，确认三张表（system_prompt、api_access_log、ai_chat_log）的列、索引正确
  - 应用 migration：`alembic upgrade head`
- **Acceptance Criteria Addressed**: NFR-3
- **Test Requirements**:
  - `programmatic` TR-7.1: migration 生成成功，无 SQLModel metadata 缺失表的问题
  - `programmatic` TR-7.2: 应用 migration 后 psql 中能看到三张表
  - `programmatic` TR-7.3: 应用启动时 lifespan 正常 warm_up 缓存（Prompt 表为空也不报错）

---

## [x] Task 8: 代码自检 + 整体验证
- **Priority**: high
- **Depends On**: Task 1~7
- **Description**:
  - 逐文件 review：检查分层一致性、命名规范、单例导出、软删除模式、响应格式
  - 跑通完整链路：启动应用 → 创建一条 Prompt → 调 AI chat → 查 api_access_log → 查 ai_chat_log → 对比 trace_id → 验证 system_prompt 注入
  - 验证敏感数据脱敏
  - 验证无递归（日志接口自身不记录到 api_access_log）
- **Acceptance Criteria Addressed**: AC-10, 所有 AC
- **Test Requirements**:
  - `human-judgement` TR-8.1: 对比现有 ai_model_config 模块，分层结构/命名/单例风格一致
  - `programmatic` TR-8.2: 启动无报错，所有 import 正确
  - `programmatic` TR-8.3: 完整链路测试通过（创建 Prompt → AI 调用 → 查日志 → trace_id 匹配）
  - `programmatic` TR-8.4: Prompt 缓存刷新生效（PATCH 后不重启，下次调用拿新内容）
  - `programmatic` TR-8.5: 敏感字段脱敏验证
