# AI 架构文档生成 - The Implementation Plan

## [x] Task 1: 创建 docs 目录 + 生成 LangChain 与多模型编排文档
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 创建 `docs/ai-architecture/` 目录
  - 编写 `01-langchain-and-orchestration.md`，覆盖：
    - 架构总览图（四层：路由 → Dispatcher → Registry → Provider 实现）
    - LangChain 角色：ChatDeepSeek / ChatOpenAI / bind_tools / astream / ainvoke
    - 消息模型双向转换：`_to_langchain_messages` / `_to_dict_messages`
    - Provider 抽象基类设计（chat / chat_stream / chat_stream_with_tools 三方法）
    - ProviderRegistry 注册机制（模块加载时副作用注册）
    - AIDispatcher 调度流程：resolve → check_capability → _build_identity_system → 获取 provider → 调用
    - 身份系统提示词注入逻辑（model_name + model_code + 当前时间 + DB prompt + user system）
    - 能力校验（supports_thinking / supports_tools）
    - thinking 双通道：LangChain 路径 vs 原生 httpx `_stream_raw` 路径（为什么分裂）
    - 工具调用循环：bind_tools + 最多 3 次迭代 + 耗尽后强制最终回答
    - 日志包装：wrap_stream_for_logging 如何收集 chunk 并入队
    - 新增一个模型的完整步骤
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-5
- **Test Requirements**:
  - `programmatic` TR-1.1: `docs/ai-architecture/01-langchain-and-orchestration.md` 文件存在
  - `human-judgement` TR-1.2: 文档中所有代码文件路径与函数名与实际仓库一致
  - `human-judgement` TR-1.3: 新增模型步骤清晰可操作

## [x] Task 2: 生成 SSE 流式处理文档
- **Priority**: high
- **Depends On**: Task 1（目录创建）
- **Description**:
  - 编写 `02-sse-streaming.md`，覆盖：
    - 完整链路图：Provider → Dispatcher → _event_generator → build_sse → StreamingResponse → 前端
    - EventType 枚举完整列表（表格：type 值、字段、含义、触发阶段）
    - StreamChunk 类型定义（Union[str, StreamEvent]）
    - _event_generator 的状态机：thinking_started/ended、content_started/ended、usage_data 收集
    - 标准事件序列时序图（正常流式对话完整序列）
    - 带工具调用的事件序列
    - build_sse 函数实现细节（bytes 拼接格式）
    - StreamingResponse headers 含义（Cache-Control、Connection、X-Accel-Buffering）
    - 遇到的问题与解决方案（5 个）：
      1. LangChain 清除 reasoning_content → 原生 httpx
      2. EventSourceResponse keepalive task → 手动 bytes
      3. httpx read timeout → read=None
      4. 工具循环耗尽 → 强制最终回答
      5. 截断流导致 Done 缺失 → 完整收集
    - 前端消费示例（EventSource / fetch + ReadableStream）
- **Acceptance Criteria Addressed**: AC-3, AC-4, AC-5
- **Test Requirements**:
  - `programmatic` TR-2.1: `docs/ai-architecture/02-sse-streaming.md` 文件存在
  - `human-judgement` TR-2.2: 每个 EventType 的 JSON 字段定义完整且与 base.py 中的 StreamEvent 一致
  - `human-judgement` TR-2.3: 5 个问题与解决方案描述清晰，根因和解决手段都有

## [x] Task 3: 最终校验
- **Priority**: medium
- **Depends On**: Task 1, Task 2
- **Description**:
  - 检查两份文档是否有遗漏的代码引用
  - 检查事件序列描述是否与 `ai.py` 中 `_event_generator` 的实际逻辑一致
  - 确认问题清单覆盖了 memory 中记录的所有坑
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3, AC-4
- **Test Requirements**:
  - `programmatic` TR-3.1: 两份 md 文件都能被 UTF-8 正常读取
  - `human-judgement` TR-3.2: 通读一遍，无明显错误或与代码不符
