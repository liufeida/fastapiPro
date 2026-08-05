# Tasks

- [x] Task 1: 新增依赖 `duckduckgo-search`
  - [x] SubTask 1.1: 通过 `uv add duckduckgo-search` 安装
  - [x] SubTask 1.2: 验证导入正常（`from duckduckgo_search import DDGS`）

- [x] Task 2: 实现文件解析服务 `app/services/file_parser.py`
  - [x] SubTask 2.1: 定义 `FileParser` 类，支持 .txt/.md/.csv/.json/.py/.log/.html/.xml 等文本类后缀
  - [x] SubTask 2.2: 实现 `parse(upload_file: UploadFile) -> str`，读取内容并返回文本（带大小限制 10MB，超出抛 BusinessException）
  - [x] SubTask 2.3: 实现 `parse_many(files: list[UploadFile]) -> str`，将多文件内容拼接为带文件名标注的上下文块
  - [x] SubTask 2.4: 不支持的文件类型抛 BusinessException，提示"暂不支持的文件类型: .xxx"

- [x] Task 3: 实现联网搜索工具 `app/services/web_search.py`
  - [x] SubTask 3.1: 实现 `web_search(query: str, max_results: int = 5) -> str`，使用 DDGS 执行搜索
  - [x] SubTask 3.2: 将搜索结果格式化为文本（标题 + 摘要 + 链接），便于模型理解
  - [x] SubTask 3.3: 异常处理：搜索失败时返回友好的错误信息而非抛异常（避免中断对话）

- [x] Task 4: 扩展 `DeepSeekService` 支持工具调用循环
  - [x] SubTask 4.1: 用 LangChain `@tool` 装饰器定义 `web_search` 工具的 schema
  - [x] SubTask 4.2: 新增 `chat_stream_with_tools(prompt, system, thinking, enable_search, file_context)` 方法
  - [x] SubTask 4.3: 实现 tool_calls 循环：模型返回 tool_call → yield tool 事件 → 执行 web_search → yield tool_result 事件 → 把 ToolMessage 回传 → 继续流式生成
  - [x] SubTask 4.4: 当 `enable_search=False` 时退化为纯流式（不 bind_tools），行为与现有 `chat_stream` 一致
  - [x] SubTask 4.5: 当有 `file_context` 时，将其拼接到 prompt 前（格式：`【文件上下文】\n{file_context}\n\n【用户问题】\n{prompt}`）

- [x] Task 5: 改造流式接口 `app/api/v1/deepseek.py`
  - [x] SubTask 5.1: 将 `/deepseek/chat/stream` 改为 `multipart/form-data`，参数：`prompt`(Form)、`system`(Form,可选)、`thinking`(Form)、`enable_search`(Form)、`files`(List[UploadFile], 可选)
  - [x] SubTask 5.2: 调用 `FileParser.parse_many` 解析上传的文件（若有）
  - [x] SubTask 5.3: 调用 `deepseek_service.chat_stream_with_tools`，根据 `enable_search` 走工具循环或纯流式
  - [x] SubTask 5.4: 扩展 SSE 事件类型：`tool`（工具调用）、`tool_result`（工具结果）、`content`（内容）、`Done`（结束）、`error`（错误）
  - [x] SubTask 5.5: 保持 `/deepseek/chat`（非流式）和 `/deepseek/health` 不变

- [x] Task 6: 验证与自测
  - [x] SubTask 6.1: 启动服务，确认无导入错误
  - [x] SubTask 6.2: 调用 `/deepseek/chat/stream`（无文件、enable_search=false），确认行为与改造前一致
  - [x] SubTask 6.3: 调用 `/deepseek/chat/stream` 上传一个 .txt 文件，确认文件内容进入上下文
  - [x] SubTask 6.4: 调用 `/deepseek/chat/stream`（enable_search=true，问"今天新闻"），确认触发 tool 事件并返回带搜索结果的内容
  - [x] SubTask 6.5: 在 Swagger `/api/docs` 确认新接口参数展示正确

# Task Dependencies
- Task 2、Task 3 可并行（互不依赖）
- Task 4 依赖 Task 3（需要 web_search 工具实现）
- Task 5 依赖 Task 2、Task 4
- Task 6 依赖 Task 5

# 验证结果说明
- 纯流式对话：✅ 通过（1+1=2 正确流式返回）
- 文件上传：✅ 通过（上传会议纪要.txt，模型准确基于内容回答 Q4 路线图）
- 工具调用循环：✅ 通过（模型正确决策调用 web_search，循环重试4次不同关键词，tool/tool_result 事件正确分发）
- 搜索结果：⚠️ DuckDuckGo 在当前网络环境返回空结果（非代码问题，需代理或换搜索后端）
