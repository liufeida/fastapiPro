# SSE 事件类型增强 - 产品需求文档

## Overview
- **Summary**: 为后端 SSE 流式对话接口新增生命周期事件、边界事件和元数据事件，让前端能够精确追踪每个阶段（思考/内容/工具调用）的开始与结束，并获取 token 用量统计。
- **Purpose**: 当前只有 `thinking`/`content`/`tool`/`tool_result`/`Done`/`error` 六种事件，缺乏生命周期边界和元数据，导致前端无法精确控制渲染节奏（如思考动画何时启动/停止、工具调用状态展示），也无法展示 token 用量。
- **Target Users**: 使用本平台 AI 流式接口的前端开发者、Agent 框架开发者

## Goals
- 新增流开始事件（start），携带请求元信息
- 各阶段增加 start/end 边界事件（thinking_start/end、content_start/end、tool_start/end）
- 新增 usage 事件，展示 token 用量
- Done 事件增强为携带 stop_reason 和完整统计
- tool_call_id 贯穿 tool → tool_result，支持精确关联
- 保持向后兼容：现有事件类型不删除，只是新增

## Non-Goals (Out of Scope)
- 不改变事件命名风格（保留小写+下划线，不改成 OpenAI Responses API 的点分命名）
- 不实现增量+累积快照双轨制（Pi 框架的 `delta` + `partial` 并存）—— 增量就是增量，前端自己累积
- 不改动 deepseek.py 旧路由的实现（但如果新框架改动需要联动则同步更新）
- 不支持多模态 content_part（本轮只聚焦文本+思考+工具调用场景）

## Background & Context

### 当前事件体系
```
content     {"content": "..."}    # 内容增量
thinking    {"reasoning": "..."}  # 思考过程增量
tool        {"name": "...", "args": {...}}   # 工具调用决策
tool_result {"name": "...", "result": "..."} # 工具执行完毕
Done        {}                                # 流结束
error       {"message": "...", "code": N}     # 错误
```

### 业界主流做法调研

**流派 A：边界事件 + Delta 事件（Pi / Coding Agent 风格）**
```
start → thinking_start → thinking_delta* → thinking_end
      → toolcall_start → toolcall_delta* → toolcall_end
      → text_start → text_delta* → text_end → done
```
每个 delta 同时携带 `delta`（增量）和 `partial`（累积快照）。

**流派 B：资源生命周期（OpenAI Responses API 风格）**
```
response.created → response.in_progress
  → output_item.added → content_part.added
    → output_text.delta* → output_text.done
    → function_call_arguments.delta* → function_call_arguments.done
  → output_item.done → response.completed
```
REST 资源语义，item 级别细粒度。

**流派 C：简化生命周期（OpenAI-Agent / LangGraph 风格）**
```
conversation_start → message_delta* → message_complete
  → tool_call → tool_output → final_state → error
```

### 设计选择
参考 **流派 A（Pi 风格）** 为主，简化复杂度后适配现有项目：
1. 保留现有事件不变，新增边界事件和元数据
2. 不做 delta+partial 双轨（前端需要时自行累积）
3. 保持 SSE event 名称短、可读性好

## Functional Requirements

### FR-1: 流启动事件（stream_start）
SSE 流的第一条消息必须是 `start` 事件，携带：
- `request_id`: 本次请求唯一 ID（可复用 trace_id 或新生成）
- `model`: model_code
- `model_name`: 模型中文名
- `thinking`: 是否开启思考
- `enable_search`: 是否开启工具搜索
- `timestamp`: 服务端时间戳（ISO 8601）

### FR-2: 思考阶段边界事件
- `thinking_start`: 思考阶段开始（data: `{"timestamp": "..."}`）
- `thinking`: 思考增量（保持现有）
- `thinking_end`: 思考阶段结束，携带完整 reasoning：`{"reasoning": "完整思考内容", "total_chars": N}`

### FR-3: 内容输出边界事件
- `content_start`: 内容开始输出（data: `{"timestamp": "..."}`）
- `content`: 内容增量（保持现有）
- `content_end`: 内容输出结束，携带完整内容：`{"content": "完整回复", "total_chars": N}`

### FR-4: 工具调用边界事件
- `tool_start`: 工具调用开始，携带 tool_call_id：`{"tool_call_id": "...", "name": "...", "args": {...}}`
- `tool_result`: 保持现有，**新增** `tool_call_id` + `elapsed_ms` 字段：`{"tool_call_id": "...", "name": "...", "result": "...", "elapsed_ms": 123}`
- 移除原有的单独 `tool` 事件类型（被 `tool_start` 取代）—— 但为向后兼容保留一个过渡别名

### FR-5: Usage 事件
- `usage`: token 用量统计，在 `end` 事件前发送：
  ```json
  {
    "prompt_tokens": 1234,
    "completion_tokens": 456,
    "total_tokens": 1690,
    "reasoning_tokens": 200
  }
  ```
  注：非 thinking 模型 reasoning_tokens 为 0；无法获取 usage 的模型（如 Ollama）usage 事件中各字段为 null。

### FR-6: 流结束事件（end）
- `end`: 流完成终止（取代原 `Done`），携带：
  ```json
  {
    "stop_reason": "stop|length|tool|error",
    "request_id": "...",
    "elapsed_ms": 5000
  }
  ```
- 为向后兼容，旧 `Done` 事件暂不删除，但新代码应只消费 `end`

### FR-7: 错误事件保持不变
`error` 事件格式不变，但若错误发生在流启动前则直接发送 error 然后 close；若发生在流中则先发 error 再发 end（stop_reason="error"）。

### FR-8: 事件顺序约束
事件必须按以下合法序列之一出现：

```
纯对话（thinking=false, enable_search=false）:
  start → [content_start → content* → content_end] → usage → end

思考对话（thinking=true, enable_search=false）:
  start → [thinking_start → thinking* → thinking_end] → [content_start → content* → content_end] → usage → end

工具调用（enable_search=true）:
  start → [thinking_start → thinking* → thinking_end]? → content_start? → content*? → content_end?
    → [tool_start → tool_result → content_start? → content*? → content_end?]*  (可循环多次)
    → usage → end

工具调用耗尽:
  start → ...tool 循环 3 次... → content_start → content* → content_end → usage → end
```

## Non-Functional Requirements

### NFR-1: 向后兼容
- 现有前端若只消费 thinking/content/tool/tool_result/Done/error，必须正常工作
- `tool` 事件保留（与 tool_start 同时发送一次，内容相同），`Done` 事件保留（与 end 同时发送一次）

### NFR-2: 零额外延迟
- 新增事件的生成和发送不得增加超过 1ms 的延迟
- 不得引入 await 阻塞已有流逻辑

### NFR-3: 所有 Provider 统一输出
- DeepSeek、Qwen、Ollama 三个 Provider 都必须通过统一的事件转换层输出相同格式的 SSE 事件
- Provider 层产出的 StreamChunk 类型需扩展以承载新事件

## Constraints

### Technical
- 现有 `ToolEvent` dataclass 需要扩展或重构，承载更丰富的事件元数据
- `build_sse` 函数签名不变（保持 `(event: str, data) -> bytes`）
- ai.py 路由层的 `_event_generator` 是唯一的 SSE 事件构造点（Provider 层只产出 StreamChunk，路由层统一映射为 SSE event）

### Dependencies
- 依赖 httpx 连接能拿到上游 usage 信息（部分模型不返回 usage 则 usage 字段为 null）
- 依赖 LangChain AIMessage 的 response_metadata 中 usage 字段

## Assumptions
- 前端已经能解析 JSON data payload
- 前端愿意升级以消费更多事件类型（不会只依赖旧的 Done/content 事件）
- Ollama 本地模型不返回 usage → usage 事件字段为 null

## Acceptance Criteria

### AC-1: 流启动事件
- **Given**: 发起一次 /chat/stream 请求
- **When**: SSE 连接建立后
- **Then**: 第一条 SSE 事件必须是 `start`，且包含 request_id、model、thinking、enable_search、timestamp 字段
- **Verification**: `programmatic`

### AC-2: 思考阶段边界事件
- **Given**: 发起 thinking=true 的请求
- **When**: 模型开始输出 reasoning_content
- **Then**: 先收到 `thinking_start`，再收到若干 `thinking` 增量，最后收到 `thinking_end`（含完整 reasoning 文本）
- **Verification**: `programmatic`

### AC-3: 内容阶段边界事件
- **Given**: 模型输出 content
- **When**: 模型开始/结束 content 输出
- **Then**: 先收到 `content_start`，再收到若干 `content` 增量，最后收到 `content_end`（含完整 content 文本）
- **Verification**: `programmatic`

### AC-4: 工具调用关联
- **Given**: enable_search=true 且模型发起工具调用
- **When**: 工具调用开始和结束
- **Then**: 收到 `tool_start`（含 tool_call_id），工具执行完毕后收到 `tool_result`（含同一 tool_call_id + elapsed_ms），两者可精确关联
- **Verification**: `programmatic`

### AC-5: Usage 事件
- **Given**: 一次完整的非错误流式对话
- **When**: 流即将结束
- **Then**: 在 end 事件前收到 `usage` 事件，包含 prompt_tokens、completion_tokens、total_tokens
- **Verification**: `programmatic`
- **Notes**: Ollama 模型各 usage 字段为 null 也算通过

### AC-6: End 事件
- **Given**: 流正常完成
- **When**: 最后一个内容块发送完毕
- **Then**: 先发送 usage（如有），再发送 `end`（含 stop_reason="stop"、elapsed_ms、request_id）
- **Verification**: `programmatic`

### AC-7: 向后兼容（tool + Done 保留）
- **Given**: 旧前端只监听 tool 和 Done 事件
- **When**: 发起 enable_search=true 的请求
- **Then**: 仍然能收到 tool 事件（内容与 tool_start 相同）和 Done 事件（与 end 同时发送）
- **Verification**: `programmatic`

### AC-8: 全 Provider 统一输出
- **Given**: 分别用 deepseek、qwen、ollama 发起相同参数请求
- **When**: SSE 流返回
- **Then**: 三家 Provider 的事件序列类型一致（start → ... → usage → end），字段名相同
- **Verification**: `programmatic`

### AC-9: 错误场景
- **Given**: 模型调用发生异常
- **When**: 异常被捕获
- **Then**: 先发 error 事件，再发 end 事件（stop_reason="error"），然后关闭连接
- **Verification**: `programmatic`

### AC-10: 延迟测试
- **Given**: 100 个 content 增量 chunk 的流式对话
- **When**: 新旧事件体系分别运行
- **Then**: 端到端延迟差 < 1ms/chunk
- **Verification**: `programmatic`

## Open Questions
- [ ] Ollama 模型的 usage 字段获取方式？（假设 Ollama 不返回 usage，usage 事件全字段为 null）
- [ ] tool_call_id 是自己生成还是从 LangChain AIMessage.tool_calls 中提取？（应提取上游真实 tool_call_id）
