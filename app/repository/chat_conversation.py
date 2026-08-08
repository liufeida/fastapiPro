from typing import Any

from sqlalchemy import update
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.chat_conversation import ChatConversation


class ChatConversationRepository:
    """会话数据访问层。"""

    async def create(self, session: AsyncSession, data: dict) -> ChatConversation:
        """创建一条会话记录。

        Args:
            session: 数据库会话。
            data: 会话字段字典。

        Returns:
            创建好的 ChatConversation 对象。
        """
        conv = ChatConversation(**data)
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        return conv

    async def get_by_id(
        self, session: AsyncSession, conv_id: str
    ) -> ChatConversation | None:
        """根据 ID 查询会话。"""
        result = await session.execute(
            select(ChatConversation).where(ChatConversation.id == conv_id)
        )
        return result.scalar_one_or_none()

    def _apply_filters(self, stmt, **filters: Any):
        user_id = filters.get("user_id")
        if user_id:
            stmt = stmt.where(ChatConversation.user_id == user_id)
        keyword = filters.get("keyword")
        if keyword:
            stmt = stmt.where(ChatConversation.title.ilike(f"%{keyword}%"))
        return stmt

    async def list_paginated(
        self,
        session: AsyncSession,
        offset: int,
        limit: int,
        **filters: Any,
    ) -> list[ChatConversation]:
        """分页查询会话列表（已过滤 is_deleted=True，按 updated_at 倒序）。

        Args:
            session: 数据库会话。
            offset: 偏移量。
            limit: 每页数量。
            **filters: 可选过滤条件（user_id, keyword）。

        Returns:
            会话列表。
        """
        stmt = (
            select(ChatConversation)
            .where(ChatConversation.is_deleted == False)  # noqa: E712
            .order_by(ChatConversation.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        stmt = self._apply_filters(stmt, **filters)
        result = await session.execute(stmt)
        return result.scalars().all()

    async def count(self, session: AsyncSession, **filters: Any) -> int:
        """统计符合条件的会话数量（排除已删除）。"""
        stmt = select(func.count()).select_from(ChatConversation).where(
            ChatConversation.is_deleted == False  # noqa: E712
        )
        stmt = self._apply_filters(stmt, **filters)
        return await session.scalar(stmt) or 0

    async def soft_delete(self, session: AsyncSession, conv_id: str) -> bool:
        """软删除会话（将 is_deleted 置为 True）。

        Args:
            session: 数据库会话。
            conv_id: 会话 ID。

        Returns:
            是否成功更新至少一行。
        """
        stmt = (
            update(ChatConversation)
            .where(ChatConversation.id == conv_id)
            .values(is_deleted=True)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount > 0

    async def rename(
        self, session: AsyncSession, conv_id: str, title: str
    ) -> bool:
        """重命名会话。

        Args:
            session: 数据库会话。
            conv_id: 会话 ID。
            title: 新标题。

        Returns:
            是否成功更新至少一行。
        """
        stmt = (
            update(ChatConversation)
            .where(ChatConversation.id == conv_id)
            .values(title=title)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount > 0

    async def touch_updated_at(
        self, session: AsyncSession, conv_id: str
    ) -> None:
        """刷新会话 updated_at 为当前时间（使用 SQL 侧 now()，比 refresh 更高效）。"""
        stmt = (
            update(ChatConversation)
            .where(ChatConversation.id == conv_id)
            .values(updated_at=func.now())
        )
        await session.execute(stmt)
        await session.commit()

    async def update_model_code(
        self, session: AsyncSession, conv_id: str, model_code: str
    ) -> None:
        """更新会话的 model_code。"""
        stmt = (
            update(ChatConversation)
            .where(ChatConversation.id == conv_id)
            .values(model_code=model_code)
        )
        await session.execute(stmt)
        await session.commit()


chat_conversation_repository = ChatConversationRepository()
