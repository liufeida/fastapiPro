import json
import uuid

from fastapi.sse import ServerSentEvent


def build_sse(event: str, data) -> ServerSentEvent:
    """构造统一格式的 SSE 事件。

    data 统一序列化为 JSON 字符串（ensure_ascii=False，中文不转义）。
    所有 AI Provider 的流式输出必须使用此工具，保证前端收到一致的事件格式。

    Args:
        event: 事件类型（thinking/content/tool/tool_result/Done/error）
        data: dict 或 None，None 时序列化为空 dict {}

    Returns:
        ServerSentEvent 实例
    """
    if data is None:
        data = {}
    payload = json.dumps(data, ensure_ascii=False)
    return ServerSentEvent(
        raw_data=payload,
        event=event,
        id=uuid.uuid4().hex,
        retry=5000,
    )
