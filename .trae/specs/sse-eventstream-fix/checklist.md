# SSE EventStream 修复 - 验证清单

## 格式正确性（字节级）
- [x] build_sse("tool", {...}) 返回 bytes 以 `b'\n\n'` 结尾
- [x] build_sse("content", {...}) 返回 bytes 以 `b'\n\n'` 结尾
- [x] build_sse("Done", {}) 返回 bytes 以 `b'\n\n'` 结尾
- [x] build_sse("error", {...}) 返回 bytes 以 `b'\n\n'` 结尾
- [x] 连续拼接 5 个 build_sse 结果（thinking+tool+tool_result+content+Done）后，按 `\n\n` 分割得到 5 个独立事件
- [x] 每个分割出的事件能正确解析出 event 名称（如 `tool`, `content`, `Done`）
- [x] 每个分割出的事件的 data 字段能正确 JSON 反序列化

## 后端端到端验证（httpx 直接连）
- [x] enable_search=false 纯流式：60 个 content + 1 个 Done = 61 事件，全部独立
- [x] enable_search=true 带工具调用：2 tool + 2 tool_result + 2 content + 1 Done = 7 事件，全部独立
- [x] thinking=true 思考模式：30 thinking + 8 content + 1 Done = 39 事件，全部独立
- [x] Content-Type 正确：`text/event-stream; charset=utf-8`

## 浏览器 EventStream 验证（需用户手动确认）
- [ ] Chrome DevTools Network → EventStream tab 能看到 tool 事件
- [ ] Chrome DevTools Network → EventStream tab 能看到 tool_result 事件
- [ ] Chrome DevTools Network → EventStream tab 能看到 content 事件
- [ ] Chrome DevTools Network → EventStream tab 能看到 Done 事件
- [ ] 每个事件有独立的 event type 和 data 显示

## 回归检查
- [x] middleware.py 的 stream_wrapper 不截断流（65 chunks → 65 events）
- [x] deepseek.py 路由（使用 EventSourceResponse）行为不变（health check 200）
- [x] ai.py 路由发出完整 Done 事件
- [x] enable_search=false 的纯流式场景正常
- [x] thinking=true 的思考模式正常（thinking 事件也能独立显示）

## 代码质量
- [x] 仅修改了 `app/services/ai/sse.py` 一个文件
- [x] 修改是最小改动（一行）
- [x] Python 语法检查通过 (`python -m py_compile`)
