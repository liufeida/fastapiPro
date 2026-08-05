# 增强流式对话接口：文件上传与联网搜索 Spec

## Why
当前 `/deepseek/chat/stream` 接口只能接受纯文本 prompt，无法处理用户上传的文件（如 PDF/TXT/图片），也不能联网获取实时信息。这与市面上主流的 DeepSeek 应用（如官网对话框、各类 RAG/Agent 产品）能力存在差距，限制了使用场景。

## What Changes
- **新增**：流式对话接口支持 multipart/form-data，可同时上传多个文件 + 文本 prompt
- **新增**：流式对话接口支持 `enable_search` 开关，开启后模型可通过 tool_calls 触发联网搜索
- **新增**：文件解析服务 `FileParser`，支持纯文本类文件（.txt/.md/.csv/.json/.py/.log 等）直接读取内容
- **新增**：联网搜索工具 `web_search`，通过 LangChain `bind_tools` 注册为 DeepSeek 可调用工具
- **新增**：搜索结果 SSE 事件类型 `tool`，前端可区分展示"正在搜索 / 搜索结果 / 最终回答"
- **MODIFIED**：`DeepSeekService` 扩展 `chat_stream_with_tools` 方法，支持工具调用循环（模型决策 → 执行工具 → 结果回传 → 继续生成）
- **不改动**：现有 `/deepseek/chat`（非流式）和 `/deepseek/health` 保持不变，避免影响已调通的接口

## Impact
- Affected code:
  - `app/api/v1/deepseek.py`（流式接口改造为支持文件上传 + search 开关）
  - `app/services/deepseek.py`（新增工具调用循环逻辑）
  - 新增 `app/services/file_parser.py`（文件解析）
  - 新增 `app/services/web_search.py`（联网搜索工具实现）
- Dependencies: 需新增 `duckduckgo-search`（免费、无需 API Key 的搜索后端）

## 市面实现调研结论
经查阅 DeepSeek 官方文档（api-docs.deepseek.com/guides/tool_calls）与主流实践：
1. **DeepSeek 原生不提供联网搜索和文件上传能力**——官方文档明确 "the model itself does not execute specific functions"，工具的实际执行由开发者提供。
2. **文件上传**：通用做法是后端先解析文件为文本，再拼到 prompt 上下文里（DeepSeek 不支持像 OpenAI 那样的 file_id 引用）。
3. **联网搜索**：通过 OpenAI 兼容的 `tools` 参数（DeepSeek 完全支持）注册 `web_search` 工具，模型在需要时返回 `tool_calls`，后端执行搜索后把结果以 `role: tool` 消息回传，模型再生成最终回答。LangChain 的 `bind_tools` + `astream` 原生支持这套循环。
4. **搜索后端选型**：DuckDuckGo（`duckduckgo-search` 库）免费且无需 Key，适合起步；后续若需更高稳定度可换 Bing/Tavily/Serper。

## ADDED Requirements

### Requirement: 流式对话支持文件上传
系统 SHALL 允许用户在调用 `/deepseek/chat/stream` 时以 multipart/form-data 形式上传多个文件，并将文件解析后的文本内容作为上下文拼接到用户 prompt 前。

#### Scenario: 上传单个文本文件
- **WHEN** 用户上传一个 `notes.txt`（内容为"会议纪要..."）并提问"总结一下"
- **THEN** 系统将文件内容拼接到 prompt，模型基于文件内容生成总结

#### Scenario: 上传不支持的文件类型
- **WHEN** 用户上传一个 `.exe` 文件
- **THEN** 系统返回业务异常，提示"暂不支持的文件类型"

#### Scenario: 同时上传多个文件
- **WHEN** 用户上传 `a.txt` 和 `b.md` 并提问"对比这两个文件"
- **THEN** 系统解析两个文件内容，一并提供给模型

### Requirement: 流式对话支持联网搜索
系统 SHALL 提供 `enable_search` 参数，开启后通过 LangChain `bind_tools` 向 DeepSeek 注册 `web_search` 工具，模型可在需要时调用以获取实时信息。

#### Scenario: 开启搜索且模型需要联网
- **WHEN** `enable_search=true` 且用户问"今天北京天气如何"
- **THEN** 模型返回 `web_search` tool_call，后端执行搜索，将结果回传，模型基于结果生成回答；前端通过 `event: tool` 收到搜索状态

#### Scenario: 开启搜索但模型不需要联网
- **WHEN** `enable_search=true` 且用户问"1+1 等于几"
- **THEN** 模型直接生成回答，不触发工具调用，行为与未开启搜索一致

#### Scenario: 关闭搜索
- **WHEN** `enable_search=false`（默认）
- **THEN** 不注册任何工具，行为与当前实现完全一致

### Requirement: 文件解析服务
系统 SHALL 提供统一的文件解析能力，将常见文本类文件（.txt/.md/.csv/.json/.py/.log/.html/.xml 等）解析为纯文本。

#### Scenario: 解析支持的文件
- **WHEN** 解析 `report.md`
- **THEN** 返回文件全文文本

#### Scenario: 文件超过大小限制
- **WHEN** 文件大于 10MB
- **THEN** 抛出业务异常，提示文件过大

### Requirement: SSE 事件类型扩展
系统 SHALL 在流式接口中扩展 SSE 事件类型，让前端能区分展示不同阶段。

#### Scenario: 工具调用阶段
- **WHEN** 模型决定调用 `web_search`
- **THEN** 推送 `event: tool`，data 为 `{"name": "web_search", "args": {"query": "..."}}`

#### Scenario: 工具结果阶段
- **WHEN** 后端执行搜索完毕
- **THEN** 推送 `event: tool_result`，data 为搜索结果摘要

#### Scenario: 内容生成阶段
- **WHEN** 模型生成最终回答
- **THEN** 推送 `event: content`（与现有行为一致）
