from sqlalchemy import insert
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.chat_message import ChatMessage


class ChatMessageRepository:
    """会话消息数据访问层。"""

    async def create_one(self, session: AsyncSession, data: dict) -> str:
        """插入单条消息，返回新记录的 ID。"""
        result = await session.execute(
            insert(ChatMessage).values(data).returning(ChatMessage.id)
        )
        await session.commit()
        return result.scalar_one()

    async def create_batch(
        self, session: AsyncSession, records: list[dict]
    ) -> None:
        """批量插入消息记录。

        Args:
            session: 数据库会话。
            records: 消息字段字典列表，每项包含 role, content, conversation_id 等。
        """
        if not records:
            return
        stmt = insert(ChatMessage).values(records)
        await session.execute(stmt)
        await session.commit()

    async def list_by_conversation(
        self, session: AsyncSession, conv_id: str
    ) -> list[ChatMessage]:
        """查询某个会话的全部消息（按创建时间升序）。

        Args:
            session: 数据库会话。
            conv_id: 会话 ID。

        Returns:
            消息列表（时间升序）。
        """
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conv_id)
            .order_by(ChatMessage.created_at.asc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def count_by_conversation(
        self, session: AsyncSession, conv_id: str
    ) -> int:
        """统计某个会话的消息数量。"""
        stmt = (
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.conversation_id == conv_id)
        )
        return await session.scalar(stmt) or 0


chat_message_repository = ChatMessageRepository()
