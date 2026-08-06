# SSE 事件类型增强 - 验收清单

## 事件完整性
- [x] Checkpoint 1: 纯对话（thinking=false, enable_search=false）SSE 事件序列为 start → content_start → content* → content_end → usage → end → Done
- [x] Checkpoint 2: 思考对话（thinking=true）SSE 事件序列含 thinking_start → thinking* → thinking_end
- [ ] Checkpoint 3: 工具调用对话（enable_search=true）SSE 事件序列含 tool_start → tool_result，且可循环多次
- [x] Checkpoint 4: 每条 SSE 事件 data 均为合法 JSON（可通过 JSON.parse 解析）
- [x] Checkpoint 5: 错误场景先发送 error，再发送 end（stop_reason="error"）—— 代码路径已实现

## 字段正确性
- [x] Checkpoint 6: start 事件包含 request_id、model、model_name、thinking、enable_search、timestamp
- [x] Checkpoint 7: thinking_end 事件包含完整 reasoning 文本（total_chars=49 实测）
- [x] Checkpoint 8: content_end 事件包含完整 content 文本（total_chars>0 实测）
- [ ] Checkpoint 9: tool_start 与 tool_result 包含相同 tool_call_id（代码已实现，待实测）
- [ ] Checkpoint 10: tool_result 包含 elapsed_ms（代码已实现，待实测）
- [x] Checkpoint 11: usage 事件包含 prompt_tokens、completion_tokens、total_tokens、reasoning_tokens（思考场景有实际值）
- [x] Checkpoint 12: end 事件包含 stop_reason、request_id、elapsed_ms

## 向后兼容
- [x] Checkpoint 13: 旧 `tool` 事件仍然发送（与 tool_start 同时）
- [x] Checkpoint 14: 旧 `Done` 事件仍然发送（与 end 同时，实测收到）
- [x] Checkpoint 15: 现有 thinking/content/tool_result 事件 payload 结构不变

## Provider 一致性
- [ ] Checkpoint 16: deepseek、qwen、ollama 三家 Provider 输出事件类型一致
- [ ] Checkpoint 17: Ollama 的 usage 事件字段为 null（而非缺失字段）

## 代码质量
- [x] Checkpoint 18: base.py 中 StreamEvent 替换 ToolEvent 后无遗留未清理的旧引用
- [x] Checkpoint 19: 路由层 _event_generator 逻辑清晰，事件编排职责单一
- [x] Checkpoint 20: Provider 层只产出原子事件，边界事件逻辑集中在路由层
- [x] Checkpoint 21: sse.py 的 build_sse 函数签名保持不变
- [x] Checkpoint 22: 所有改动文件 import 正常（uv run python -c "import ..." 通过）

## 修复的 Bug
- [x] Bug 1: StreamEvent dataclass 缺少 reasoning_tokens 字段（导致 thinking=true 场景抛 AttributeError）
