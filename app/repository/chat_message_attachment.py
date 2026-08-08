from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.chat_message_attachment import ChatMessageAttachment


class ChatMessageAttachmentRepository:
    """消息附件数据访问层。"""

    async def create(
        self, session: AsyncSession, data: dict
    ) -> ChatMessageAttachment:
        """创建一条附件记录。

        Args:
            session: 数据库会话。
            data: 附件字段字典。

        Returns:
            创建好的 ChatMessageAttachment 对象。
        """
        attach = ChatMessageAttachment(**data)
        session.add(attach)
        await session.commit()
        await session.refresh(attach)
        return attach

    async def list_by_message(
        self, session: AsyncSession, message_id: str
    ) -> list[ChatMessageAttachment]:
        """查询某条消息的全部附件。

        Args:
            session: 数据库会话。
            message_id: 消息 ID。

        Returns:
            附件列表。
        """
        stmt = select(ChatMessageAttachment).where(
            ChatMessageAttachment.message_id == message_id
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def list_by_message_ids(
        self, session: AsyncSession, message_ids: list[str]
    ) -> dict[str, list[ChatMessageAttachment]]:
        """批量查多个消息的附件，返回 {message_id: [attachment, ...]} 映射。"""
        if not message_ids:
            return {}
        stmt = select(ChatMessageAttachment).where(
            ChatMessageAttachment.message_id.in_(message_ids)
        )
        result = await session.execute(stmt)
        attachments = result.scalars().all()
        grouped: dict[str, list[ChatMessageAttachment]] = {}
        for att in attachments:
            grouped.setdefault(att.message_id, []).append(att)
        return grouped


chat_message_attachment_repository = ChatMessageAttachmentRepository()
