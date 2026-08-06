# SSE EventStream 面板无响应问题修复 - PRD

## Overview
- **Summary**: 修复 AI 通用接口 `/api/v1/ai/chat/stream` 的 SSE 流式响应格式，使浏览器 DevTools 的 EventStream 面板能正确解析并展示每个事件
- **Purpose**: 当前响应面板能看到原始字节数据，但 EventStream 面板为空——根因是 `build_sse()` 函数输出的 SSE 流中，事件之间只用单换行分隔，缺少 SSE 规范要求的双换行分隔符
- **Target Users**: 前端开发人员（调试用）、最终用户（如果有前端 SSE 解析逻辑依赖规范格式）

## Goals
- **G1**: 修复 `build_sse()` 输出，每个 SSE 事件以 `\n\n`（空行）结束，符合 W3C SSE 规范
- **G2**: 确保所有 SSE 事件类型（tool / tool_result / content / thinking / Done / error）在浏览器 EventStream 面板中可独立识别
- **G3**: 端到端验证——从 `/api/v1/ai/chat/stream` 路由发出的流，字节级格式正确

## Non-Goals (Out of Scope)
- 不修改 provider 层（deepseek_provider.py / qwen_provider.py）的流式逻辑
- 不修改中间件（middleware.py）的 stream_wrapper 逻辑
- 不修改 `app/api/v1/deepseek.py`（该路由使用 FastAPI 原生 EventSourceResponse，格式正确）
- 不改动前端代码

## Background & Context
- **W3C SSE 规范要求**: 每个事件由一个或多个 `field: value` 行组成，事件之间用空行（blank line = `\n\n`）分隔。参考 https://html.spec.whatwg.org/multipage/server-sent-events.html
- **当前代码**: [sse.py](file:///d:/project/fastapi-demo/app/services/ai/sse.py#L4-L23) 的 `build_sse()` 构造的事件只有单 `\n` 结尾
- **字节级诊断结果**:
  - 当前输出：`b'event: tool\ndata: {...}\nevent: content\ndata: {...}\nevent: Done\ndata: {}\n'` — **零个** `\n\n`
  - 正确格式：每个事件需要以 `\n\n` 结束
- **对比**: `app/api/v1/deepseek.py` 使用 FastAPI 内置的 `ServerSentEvent` + `EventSourceResponse`，格式正确，无需修改

## Functional Requirements
- **FR-1**: `build_sse(event, data)` 返回的 bytes 必须以 `\n\n` 结尾
- **FR-2**: 多个 `build_sse()` 结果拼接后，必须能被标准 SSE 客户端解析为独立事件
- **FR-3**: `ai.py` 路由中通过 `StreamingResponse` 发出的完整流，格式必须符合 W3C SSE 规范

## Non-Functional Requirements
- **NFR-1**: 修复必须是最小改动——仅修改 `build_sse()` 返回格式，不影响调用方
- **NFR-2**: 必须兼容 `app/api/v1/ai.py` 中 `_event_generator` 对 `build_sse()` 的使用方式（直接 yield bytes）

## Constraints
- **Technical**: 
  - 修改文件仅限 `app/services/ai/sse.py`（最多再加验证脚本）
  - 不能破坏 `app/api/v1/ai.py` 中的调用逻辑
- **Dependencies**: 依赖 Python 标准库 `json`，无额外第三方库需求

## Assumptions
- 假设前端已经按 SSE 规范解析 EventSource，如果之前有兼容非标准格式的代码，修复后两者都能工作
- 假设中间件 `stream_wrapper` 只是透传 chunk（只收集预览不修改），不会破坏 SSE 格式

## Acceptance Criteria

### AC-1: build_sse 输出符合 SSE 规范
- **Given**: 调用 `build_sse("tool", {"name": "web_search"})`
- **When**: 检查返回的 bytes
- **Then**: 
  - 以 `b'\n\n'` 结尾
  - 包含 `b'event: tool\ndata: '` 前缀
  - 不含任何多余的 BOM 或特殊字符
- **Verification**: `programmatic`

### AC-2: 多个事件可被标准 SSE 解析器拆分
- **Given**: 连续调用 `build_sse("tool", ...)`, `build_sse("content", ...)`, `build_sse("Done", {})` 并拼接
- **When**: 按 SSE 规范的空行分割规则手动解析
- **Then**: 成功得到 3 个独立事件，每个事件都有 event 字段和 data 字段
- **Verification**: `programmatic`

### AC-3: 浏览器 EventStream 面板可看到独立事件
- **Given**: 后端服务启动，前端发出 chat/stream 请求（带 enable_search=true 触发 tool 调用链）
- **When**: 在 Chrome DevTools Network 面板中查看该请求的 EventStream tab
- **Then**: 可看到独立的 tool → tool_result → content → Done 事件序列，每个事件有正确的 type 和 data
- **Verification**: `human-judgment`（通过浏览器验证）

## Open Questions
- 无。根因已 100% 锁定，修复方案明确。
