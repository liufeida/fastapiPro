# SSE 事件类型增强 - 实施计划

## [x] Task 1: 重构事件数据模型（base.py）
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 将现有 `ToolEvent` dataclass 重构为通用的 `StreamEvent`，支持所有事件类型（不仅限于 tool/tool_result/thinking）
  - 新增事件类型枚举 `EventType`（start/thinking_start/thinking/thinking_end/content_start/content/content_end/tool_start/tool_result/usage/end/error）
  - 扩展数据字段：request_id、tool_call_id、stop_reason、usage 字段等
  - 保持向后兼容：`ToolEvent` 保留为 `StreamEvent` 的别名或子类
  - 更新 `StreamChunk` 类型定义
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3, AC-4
- **Test Requirements**:
  - `programmatic` TR-1.1: StreamEvent 能构造所有 11 种事件类型，字段类型正确
  - `programmatic` TR-1.2: 原 ToolEvent 引用处 import 不报错
- **Notes**: 这是基础设施层，后续所有 Provider 和路由层都依赖此模型

## [x] Task 2: 路由层统一事件映射（ai.py + dispatcher.py）
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 在 `ai.py` 的 `_event_generator` 中实现完整的事件序列编排：
    - 流启动时先发 `start` 事件（携带 request_id、model、thinking、enable_search、timestamp）
    - 累积 thinking 增量，在首块前先发 `thinking_start`，结束后发 `thinking_end`
    - 累积 content 增量，首块前先发 `content_start`，结束后发 `content_end`
    - 拦截 `tool_start` 事件（含 tool_call_id），旧 `tool` 事件作为向后兼容别名同时发送
    - tool_result 新增 elapsed_ms 计算
    - 流结束前先发 `usage`（从 Provider 累积），再发 `end`（含 stop_reason + elapsed_ms）
    - 旧 `Done` 事件保留为向后兼容别名（与 end 同时发送）
  - dispatcher 需要记录请求开始时间戳用于计算 elapsed_ms
  - 在 dispatcher 层维护 usage 累积器（各 Provider 产出后汇总）
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-9
- **Test Requirements**:
  - `programmatic` TR-2.1: 发起纯对话，收到事件序列 start → content_start → content* → content_end → usage → end → Done
  - `programmatic` TR-2.2: 发起思考对话，收到 thinking_start → thinking* → thinking_end 序列
  - `programmatic` TR-2.3: 向后兼容：tool 事件和 Done 事件仍然发送
- **Notes**: 这是核心调度层，负责把 Provider 产出的 StreamChunk 编排成完整的事件序列

## [x] Task 3: Provider 层改造（deepseek_provider.py + qwen_provider.py + ollama_provider.py）
- **Priority**: high
- **Depends On**: Task 1, Task 2
- **Description**:
  - 三个 Provider 的 `StreamChunk` 产出从 `Union[str, ToolEvent]` 迁移到新 `StreamEvent`
  - 思考阶段：Provider 只产出 thinking 增量，边界事件（thinking_start/end）由路由层统一编排
  - 内容阶段：Provider 只产出 content 增量，边界事件（content_start/end）由路由层统一编排
  - 工具调用：Provider 产出 `tool_start`（含真实 tool_call_id）和 `tool_result`（需计算 elapsed_ms）
  - 新增 usage 数据提取：
    - deepseek/qwen 从 _stream_raw 的最终 chunk 中提取 usage
    - LangChain 路径从 AIMessage.response_metadata.get("token_usage") 提取
    - ollama 产出 usage 全为 null
  - 流式函数返回 usage 元信息（需一种方式让路由层获取）
- **Acceptance Criteria Addressed**: AC-4, AC-5, AC-8
- **Test Requirements**:
  - `programmatic` TR-3.1: deepseek_provider 的 _stream_raw 能提取 usage 并返回
  - `programmatic` TR-3.2: qwen_provider 同上
  - `programmatic` TR-3.3: ollama_provider usage 为 null 字段
- **Notes**: Provider 层只负责产出"原子事件"（thinking 增量、content 增量、tool_start、tool_result、usage），边界事件编排全部上提到路由层

## [x] Task 4: 旧路由联动更新（deepseek.py）
- **Priority**: medium
- **Depends On**: Task 1, Task 2
- **Description**:
  - `app/api/v1/deepseek.py`（旧的独立路由）同步更新，使用新事件体系
  - `app/services/deepseek.py`（旧服务）同步更新 ToolEvent 引用
  - 确保两条路由（ai.py 通用 + deepseek.py 独立）输出一致的事件格式
- **Acceptance Criteria Addressed**: AC-7, AC-8
- **Test Requirements**:
  - `programmatic` TR-4.1: deepseek.py 路由的 SSE 输出与 ai.py 格式一致
- **Notes**: 旧路由已标记为 deprecated 但仍在使用，必须保持同步

## [x] Task 5: End-to-End 集成验证
- **Priority**: high
- **Depends On**: Task 1, Task 2, Task 3, Task 4
- **Description**:
  - 启动应用，用 HTTP 客户端直接消费 SSE 流
  - 覆盖场景：
    1. 纯对话（thinking=false, enable_search=false）
    2. 思考对话（thinking=true）
    3. 工具调用（enable_search=true）
    4. 错误场景（故意传无效模型名触发）
  - 验证事件顺序、字段完整性、向后兼容
- **Acceptance Criteria Addressed**: AC-1 through AC-10
- **Test Requirements**:
  - `programmatic` TR-5.1: 纯对话事件序列正确，usage 有值
  - `programmatic` TR-5.2: 思考对话有 thinking_start/end
  - `programmatic` TR-5.3: 工具调用 tool_call_id 在 tool_start → tool_result 中一致
  - `programmatic` TR-5.4: 错误场景 → error → end(stop_reason="error")
  - `programmatic` TR-5.5: 旧 tool/Done 事件仍能收到
- **Notes**: 这是最终验收，所有子任务完成后做全链路测试
