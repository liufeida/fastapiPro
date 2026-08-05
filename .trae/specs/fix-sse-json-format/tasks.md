# Tasks

- [x] Task 1: 修改 `_sse` 辅助函数，统一 JSON 序列化
  - [x] SubTask 1.1: 移除 `if isinstance(data, str)` 分支，所有 data 必须是 dict
  - [x] SubTask 1.2: 统一使用 `json.dumps(data, ensure_ascii=False)` 序列化
  - [x] SubTask 1.3: 当 data 为 None 时，转为空 dict `{}`

- [x] Task 2: 修改 content 事件，将内容放在 JSON 字段中
  - [x] SubTask 2.1: 将 `yield _sse("content", chunk)` 改为 `yield _sse("content", {"content": chunk})`

- [x] Task 3: 修改 Done 事件，使用空对象
  - [x] SubTask 3.1: 将 `yield _sse("Done", None)` 改为 `yield _sse("Done", {})`

- [x] Task 4: 更新接口文档注释
  - [x] SubTask 4.1: 在 docstring 中说明所有 SSE 事件的 data 均为 JSON 格式
  - [x] SubTask 4.2: 列出各事件的 JSON 结构示例

- [x] Task 5: 验证 SSE 输出格式
  - [x] SubTask 5.1: 启动服务，调用流式接口
  - [x] SubTask 5.2: 检查 SSE 原始输出，确认所有 data: 后都是 JSON 字符串
  - [x] SubTask 5.3: 验证中文内容未被转义为 `\uXXXX`
  - [x] SubTask 5.4: 验证包含空格的内容完整保留

# Task Dependencies
- Task 2、Task 3 依赖 Task 1（需要先修改 `_sse` 函数）
- Task 4 依赖 Task 2、Task 3
- Task 5 依赖 Task 4
