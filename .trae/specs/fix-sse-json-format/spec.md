# 修复 SSE 数据格式：统一 JSON 序列化 Spec

## Why
前端使用 hey-api 自动生成的 SSE 客户端解析 `/deepseek/chat/stream` 的流式响应时，内容中的空格会丢失。根因是 hey-api 自动生成的 SSE 解析器（serverSentEvents.gen.ts）在解析 `data:` 行时使用了贪婪正则 `/^data:\s*/`，会把 `data:` 后面的所有空白字符都当作分隔符吃掉。这个正则在自动生成的文件里，前端每次重新生成 API 客户端都会被覆盖，无法永久修复。

## What Changes
- **MODIFIED**：`/deepseek/chat/stream` 接口中，所有 SSE 事件的 `data` 部分必须用 `json.dumps()` 序列化，将文本内容放在 JSON 字段中
- **MODIFIED**：`_sse` 辅助函数不再支持直接传递纯字符串，所有 data 必须是 dict/对象
- **BREAKING**：前端需要调整 SSE 事件解析逻辑，从 JSON 字段中读取内容而非直接使用 `e.data`

## Impact
- Affected specs: DeepSeek 流式对话 SSE 事件格式
- Affected code:
  - `app/api/v1/deepseek.py`（SSE 事件构造逻辑）
  - 前端 SSE 客户端解析逻辑（需适配 JSON 格式）

## ADDED Requirements

### Requirement: SSE 数据统一 JSON 格式
系统 SHALL 在所有 SSE 事件的 `data` 部分使用 JSON 格式发送数据，即使是纯文本内容也必须放在 JSON 字段中。JSON 字符串内的空格不会被 SSE 正则影响。

#### Scenario: 内容生成事件
- **WHEN** 模型生成内容块 "hello world"（中间有空格）
- **THEN** 后端发送 `data: {"content": "hello world"}`，前端收到完整内容含空格

#### Scenario: 思考过程事件
- **WHEN** 模型产生思考内容 "让我想想...\n这需要推理"
- **THEN** 后端发送 `data: {"reasoning": "让我想想...\n这需要推理"}`，前端收到完整思考内容

#### Scenario: 空内容或纯空格
- **WHEN** 模型生成的内容块是单个空格 " " 或空字符串 ""
- **THEN** 后端发送 `data: {"content": " "}` 或 `data: {"content": ""}`，前端不丢失内容

#### Scenario: 结束事件
- **WHEN** 流式对话结束
- **THEN** 后端发送 `data: {}`（空 JSON 对象）

### Requirement: 事件格式规范
所有 SSE 事件 MUST 严格遵循以下格式：
- `event: <type>` 字段，值为 `content` / `thinking` / `tool` / `tool_result` / `Done` / `error`
- `data: <json>` 字段，内容为 JSON 字符串
- 每个事件以双换行 `\n\n` 结尾
- `ensure_ascii=False`：中文不要被转义成 `\uXXXX`

#### Scenario: 工具调用事件
- **WHEN** 模型决定调用 web_search 工具
- **THEN** 发送 `event: tool` + `data: {"name": "web_search", "args": {"query": "..."}}`

#### Scenario: 工具结果事件
- **WHEN** 后端执行搜索完毕
- **THEN** 发送 `event: tool_result` + `data: {"name": "web_search", "result": "..."}`

#### Scenario: 错误事件
- **WHEN** 发生业务异常或系统异常
- **THEN** 发送 `event: error` + `data: {"message": "...", "code": 500}`

## MODIFIED Requirements

### Requirement: _sse 辅助函数
**现有**：`_sse(event: str, data)` 支持字符串和 dict 两种 data 类型
**修改为**：`_sse(event: str, data)` 仅支持 dict 类型，统一使用 `json.dumps(data, ensure_ascii=False)` 序列化

### Requirement: 流式接口 SSE 产出逻辑
**现有**：
- content 事件：`yield _sse("content", chunk)`（chunk 是字符串）
- thinking 事件：`yield _sse("thinking", {"reasoning": chunk.result or ""})`
- tool 事件：`yield _sse("tool", {"name": chunk.name, "args": chunk.args or {}})`
- tool_result 事件：`yield _sse("tool_result", {"name": chunk.name, "result": chunk.result or ""})`
- Done 事件：`yield _sse("Done", None)`

**修改为**：
- content 事件：`yield _sse("content", {"content": chunk})`
- thinking 事件：`yield _sse("thinking", {"reasoning": chunk.result or ""})`（保持不变）
- tool 事件：`yield _sse("tool", {"name": chunk.name, "args": chunk.args or {}})`（保持不变）
- tool_result 事件：`yield _sse("tool_result", {"name": chunk.name, "result": chunk.result or ""})`（保持不变）
- Done 事件：`yield _sse("Done", {})`（空对象而非 None）
- error 事件：`yield _sse("error", {"message": "...", "code": 500})`（保持不变）

## REMOVED Requirements
无

## 前端适配说明
前端解析示例（TypeScript）：
```typescript
eventSource.addEventListener('content', (e) => {
  const data = JSON.parse(e.data);
  console.log(data.content); // 获取内容文本
});

eventSource.addEventListener('thinking', (e) => {
  const data = JSON.parse(e.data);
  console.log(data.reasoning); // 获取思考内容
});

eventSource.addEventListener('Done', (e) => {
  // data 是 {}，无需处理
});
```
