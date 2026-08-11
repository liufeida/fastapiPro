from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.chat_conversation import ChatConversation
from app.repository.chat_conversation import chat_conversation_repository
from app.repository.chat_message import chat_message_repository


class ChatConversationService:
    """会话业务服务层——封装会话创建、查询、消息持久化等业务逻辑。"""

    async def create_conversation(
        self,
        session: AsyncSession,
        user_id: str | None = None,
        model_code: str | None = None,
        initial_title: str | None = None,
    ) -> ChatConversation:
        """创建新会话。

        Args:
            session: 数据库会话。
            user_id: 用户 ID。
            model_code: 模型编码。
            initial_title: 初始标题，为空时使用默认值 "新对话"。

        Returns:
            创建好的 ChatConversation 对象。
        """
        title = initial_title or "新对话"
        data: dict = {"title": title}
        if user_id is not None:
            data["user_id"] = user_id
        if model_code is not None:
            data["model_code"] = model_code
        return await chat_conversation_repository.create(session, data)

    async def ensure_conversation(
        self,
        session: AsyncSession,
        conversation_id: str | None = None,
        user_id: str | None = None,
        model_code: str | None = None,
        first_prompt: str | None = None,
    ) -> ChatConversation:
        """确保会话存在——有 ID 就查，查不到或没 ID 就新建。

        新建时如果 first_prompt 不为空，取前 30 字符作为标题。
        如果请求传了不同的 model_code，自动更新会话。

        Args:
            session: 数据库会话。
            conversation_id: 会话 ID，存在时优先查询。
            user_id: 用户 ID。
            model_code: 模型编码。
            first_prompt: 首轮用户 prompt，用于自动生成标题。

        Returns:
            已存在或新创建的 ChatConversation 对象。
        """
        if conversation_id:
            conv = await chat_conversation_repository.get_by_id(session, conversation_id)
            if conv:
                if model_code and conv.model_code != model_code:
                    await chat_conversation_repository.update_model_code(
                        session, conversation_id, model_code
                    )
                    conv.model_code = model_code
                return conv
        auto_title = None
        if first_prompt:
            auto_title = first_prompt[:10]
        return await self.create_conversation(
            session,
            user_id=user_id,
            model_code=model_code,
            initial_title=auto_title,
        )

    async def soft_delete(
        self, session: AsyncSession, conversation_id: str
    ) -> bool:
        """软删除会话。"""
        return await chat_conversation_repository.soft_delete(session, conversation_id)

    async def rename(
        self, session: AsyncSession, conversation_id: str, title: str
    ) -> bool:
        """重命名会话。"""
        return await chat_conversation_repository.rename(session, conversation_id, title)

    async def save_user_message(
        self,
        session: AsyncSession,
        conversation_id: str,
        user_content: str,
        model_code: str | None = None,
    ) -> str:
        """流式开始前立即写入 user 消息，保证即使流中断用户消息也能留存。

        Args:
            session: 数据库会话。
            conversation_id: 会话 ID。
            user_content: 用户消息内容。
            model_code: 产生此消息的模型编码（可选）。

        Returns:
            新消息的 ID。
        """
        data = {
            "role": "user",
            "content": user_content,
            "conversation_id": conversation_id,
            "model_code": model_code,
        }
        msg_id = await chat_message_repository.create_one(session, data)
        await chat_conversation_repository.touch_updated_at(session, conversation_id)
        return msg_id

    async def save_assistant_message(
        self,
        session: AsyncSession,
        conversation_id: str,
        assistant_content: str,
        thinking_content: str | None = None,
        tokens_input: int | None = None,
        tokens_output: int | None = None,
        tool_calls: dict | None = None,
        tool_call_id: str | None = None,
        model_code: str | None = None,
    ) -> str:
        """流式正常结束后写入 assistant 消息。

        Args:
            session: 数据库会话。
            conversation_id: 会话 ID。
            assistant_content: 助手消息内容。
            thinking_content: 助手思考链内容（可选）。
            tokens_input: 输入 token 数（可选）。
            tokens_output: 输出 token 数（可选）。
            tool_calls: assistant 消息的 tool_calls JSON（可选）。
            tool_call_id: tool 消息关联的 ID（可选）。
            model_code: 产生此消息的模型编码（可选）。

        Returns:
            新消息的 ID。
        """
        data = {
            "role": "assistant",
            "content": assistant_content,
            "thinking_content": thinking_content,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "conversation_id": conversation_id,
            "model_code": model_code,
        }
        if tool_calls is not None:
            data["tool_calls"] = tool_calls
        if tool_call_id is not None:
            data["tool_call_id"] = tool_call_id
        msg_id = await chat_message_repository.create_one(session, data)
        await chat_conversation_repository.touch_updated_at(session, conversation_id)
        return msg_id

    async def record_message_pair(
        self,
        session: AsyncSession,
        conversation_id: str,
        user_content: str,
        assistant_content: str,
        thinking_content: str | None = None,
        tokens_input: int | None = None,
        tokens_output: int | None = None,
    ) -> None:
        """批量写入一条 user + 一条 assistant 消息，并刷新会话 updated_at。

        Args:
            session: 数据库会话。
            conversation_id: 会话 ID。
            user_content: 用户消息内容。
            assistant_content: 助手消息内容。
            thinking_content: 助手思考链内容（可选）。
            tokens_input: 输入 token 数（可选）。
            tokens_output: 输出 token 数（可选）。
        """
        records = [
            {
                "role": "user",
                "content": user_content,
                "conversation_id": conversation_id,
            },
            {
                "role": "assistant",
                "content": assistant_content,
                "thinking_content": thinking_content,
                "tokens_input": tokens_input,
                "tokens_output": tokens_output,
                "conversation_id": conversation_id,
            },
        ]
        await chat_message_repository.create_batch(session, records)
        await chat_conversation_repository.touch_updated_at(session, conversation_id)


chat_conversation_service = ChatConversationService()
