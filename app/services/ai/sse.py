import json


def build_sse(event: str, data) -> bytes:
    """构造 SSE 事件（直接返回 bytes，兼容 StreamingResponse）。

    SSE 格式:
        event: {event}\\n
        data: {json}\\n
        \\n

    Args:
        event: 事件类型（thinking/content/tool/tool_result/Done/error）
        data: dict 或 None

    Returns:
        SSE 格式的 bytes
    """
    if data is None:
        data = {}
    payload = json.dumps(data, ensure_ascii=False)
    lines = [f"event: {event}", f"data: {payload}"]
    return ("\n".join(lines) + "\n\n").encode("utf-8")
