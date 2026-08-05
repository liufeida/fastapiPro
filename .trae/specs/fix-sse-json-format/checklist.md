# Checklist

- [x] `_sse` 函数不再支持字符串类型的 data，统一处理 dict
- [x] content 事件的 data 格式为 `{"content": "..."}`
- [x] thinking 事件的 data 格式为 `{"reasoning": "..."}`
- [x] tool 事件的 data 格式为 `{"name": "...", "args": {...}}`
- [x] tool_result 事件的 data 格式为 `{"name": "...", "result": "..."}`
- [x] Done 事件的 data 格式为 `{}`（空对象）
- [x] error 事件的 data 格式为 `{"message": "...", "code": ...}`
- [x] 所有 JSON 序列化使用 `ensure_ascii=False`，中文不被转义
- [x] SSE 原始输出中，`data:` 后面都是合法的 JSON 字符串
- [x] 接口文档注释已更新，说明 JSON 格式
- [x] 流式接口调用正常，各事件类型正确分发
