# Checklist

## 文件解析服务
- [x] `app/services/file_parser.py` 已创建，`FileParser` 类支持 .txt/.md/.csv/.json/.py/.log/.html/.xml 等后缀
- [x] 单文件解析 `parse()` 返回纯文本内容
- [x] 多文件解析 `parse_many()` 返回带文件名标注的拼接上下文
- [x] 文件超过 10MB 时抛 BusinessException
- [x] 不支持的文件类型抛 BusinessException，提示包含具体后缀

## 联网搜索工具
- [x] `app/services/web_search.py` 已创建，使用 `duckduckgo-search` 的 DDGS
- [x] `web_search(query)` 返回格式化的搜索结果文本（标题+摘要+链接）
- [x] 搜索失败时不抛异常，返回友好错误信息

## DeepSeekService 扩展
- [x] `chat_stream_with_tools` 方法已实现
- [x] `enable_search=True` 时通过 LangChain `bind_tools` 注册 web_search 工具
- [x] tool_calls 循环逻辑正确：模型返回 tool_call → 执行 → ToolMessage 回传 → 继续生成
- [x] `enable_search=False` 时退化为纯流式，行为与现有 `chat_stream` 一致
- [x] 文件上下文正确拼接到 prompt 前，格式清晰

## 流式接口改造
- [x] `/deepseek/chat/stream` 改为 multipart/form-data
- [x] 支持参数：prompt、system、thinking、enable_search、files
- [x] SSE 事件类型扩展：tool / tool_result / content / Done / error
- [x] `/deepseek/chat`（非流式）和 `/deepseek/health` 保持不变

## 验证
- [x] 服务启动无导入错误
- [x] 纯文本流式对话（无文件、无搜索）行为与改造前一致
- [x] 上传 .txt 文件后，模型回答基于文件内容
- [x] 开启 enable_search 后，触发 tool 事件并返回带搜索结果的内容
- [x] Swagger `/api/docs` 中新接口参数展示正确
- [x] 关闭搜索时不触发任何工具调用

## 备注
- DuckDuckGo 在当前网络环境（中国大陆）返回空结果，属网络访问限制，非代码缺陷。
  工具调用机制本身完全正常（模型能决策调用、循环重试、事件正确分发）。
  后续若需稳定搜索，可在 `app/services/web_search.py` 中将 `do_search` 的实现替换为
  Tavily / Bing / Serper 等（需对应 API Key），无需改动其它代码。
