# SSE EventStream 面板无响应问题修复 - 实施计划

## [x] Task 1: 修复 build_sse() 函数输出格式
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 修改 `app/services/ai/sse.py` 中的 `build_sse()` 函数
  - 将事件结尾从单 `\n` 改为双 `\n\n`，符合 W3C SSE 规范
  - 最小改动：将末尾空字符串移除，改为显式拼接 `\n\n`
- **Acceptance Criteria Addressed**: AC-1, AC-2
- **Test Requirements**:
  - `programmatic` TR-1.1: 调用 `build_sse("test", {"k": "v"})`，返回 bytes 必须以 `b'\n\n'` 结尾
  - `programmatic` TR-1.2: 连续拼接 3 个 build_sse 结果（tool + content + Done），检查 `b'\n\n'` 出现次数 >= 3
  - `programmatic` TR-1.3: 编译检查 `python -m py_compile app/services/ai/sse.py` 通过
- **Notes**: 
  - 一行修改即可，不要改其他逻辑
  - 目标文件：`app/services/ai/sse.py` 第 22-23 行
  - 旧代码：`lines = [f"event: {event}", f"data: {payload}", ""]` + `"\n".join(lines).encode("utf-8")`
  - 新代码：`lines = [f"event: {event}", f"data: {payload}"]` + `("\n".join(lines) + "\n\n").encode("utf-8")`

## [x] Task 2: 单元级格式验证
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 运行验证脚本确认修复后的 SSE 格式正确
  - 模拟 ai.py 的 _event_generator 产出多个事件，拼接后检查字节流
- **Acceptance Criteria Addressed**: AC-1, AC-2
- **Test Requirements**:
  - `programmatic` TR-2.1: 构造完整事件链（thinking + tool + tool_result + content + Done），拼接后手动按 `\n\n` 分割，得到的事件数量正确
  - `programmatic` TR-2.2: 每个分割出的事件能被正确解析出 event 名称和 JSON data
- **Notes**: 用一次性 python -c 脚本验证，不创建正式测试文件

## [x] Task 3: 端到端浏览器验证
- **Priority**: high
- **Depends On**: Task 2
- **Description**: 
  - 启动后端服务，在浏览器中触发 chat/stream 请求（enable_search=true）
  - 检查 Chrome DevTools Network 面板的 EventStream tab 是否能看到独立事件
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `human-judgement` TR-3.1: EventStream 面板可见 tool, tool_result, content, Done 独立事件
  - `human-judgement` TR-3.2: 响应面板和 EventStream 面板数据一致
- **Notes**: 需要启动后端并在前端页面测试

## [x] Task 4: 回归检查 - 不破坏现有功能
- **Priority**: medium
- **Depends On**: Task 3
- **Description**: 
  - 确认 middleware.py 的 stream_wrapper 正常透传（不截断流）
  - 确认 deepseek.py 路由（使用 FastAPI 原生 EventSourceResponse）未受影响
  - 确认 ai.py 路由的 Done 事件仍会发送
- **Acceptance Criteria Addressed**: AC-2, AC-3
- **Test Requirements**:
  - `programmatic` TR-4.1: ai.py 路由发出的完整流中，Done 事件存在且格式正确
  - `human-judgement` TR-4.2: 前端最终能收到完整回复，无截断
