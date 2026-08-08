from sqlmodel.ext.asyncio.session import AsyncSession

from app.repository.chat_message import chat_message_repository


MAX_HISTORY_MESSAGES = 50


async def build_messages_for_provider(
    session: AsyncSession,
    conversation_id: str,
    system_prompt: str,
    current_user_prompt: str,
    file_context: str | None = None,
) -> list[dict]:
    """组装传给 Provider 的完整 messages 数组。

    顺序：[system_prompt] + [历史消息(只取content)] + [当前user消息]。
    thinking_content 绝不传入模型上下文。
    file_context 拼到当前 user prompt 开头。

    TODO: 未来多模态：查 chat_message_attachment，如果有 image 类型，将 content 改为数组格式。
    TODO: 预留 token 裁剪常量 MAX_HISTORY_MESSAGES 或 MAX_HISTORY_TOKENS。

    Args:
        session: 数据库会话。
        conversation_id: 会话 ID。
        system_prompt: 系统提示词。
        current_user_prompt: 当前轮用户输入。
        file_context: 文件上下文（可选）。

    Returns:
        传给 LLM Provider 的 messages 数组。
    """
    history = await chat_message_repository.list_by_conversation(session, conversation_id)

    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    for msg in history:
        if msg.role == "tool":
            messages.append({
                "role": "tool",
                "tool_call_id": msg.tool_call_id or "",
                "content": msg.content or "",
            })
        elif msg.role == "assistant":
            entry: dict = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                entry["tool_calls"] = msg.tool_calls
            messages.append(entry)
        else:
            messages.append({"role": msg.role, "content": msg.content or ""})

    if file_context:
        final_prompt = f"【文件上下文】\n{file_context}\n\n【用户问题】\n{current_user_prompt}"
    else:
        final_prompt = current_user_prompt

    messages.append({"role": "user", "content": final_prompt})
    return messages
