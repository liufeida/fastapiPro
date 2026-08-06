from typing import Any

from sqlalchemy import insert, nullslast
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.ai_chat_log import AIChatLog


class AIChatLogRepository:
    """AI LLM 调用日志数据访问层。"""

    async def create_batch(self, session: AsyncSession, records: list[dict]) -> None:
        """批量插入日志记录。"""
        if not records:
            return
        stmt = insert(AIChatLog).values(records)
        await session.execute(stmt)
        await session.commit()

    async def get_by_id(self, session: AsyncSession, log_id: str) -> AIChatLog | None:
        result = await session.execute(select(AIChatLog).where(AIChatLog.id == log_id))
        return result.scalar_one_or_none()

    def _apply_filters(self, stmt, **filters: Any):
        trace_id = filters.get("trace_id")
        if trace_id:
            stmt = stmt.where(AIChatLog.trace_id == trace_id)
        model_code = filters.get("model_code")
        if model_code:
            stmt = stmt.where(AIChatLog.model_code == model_code)
        provider_code = filters.get("provider_code")
        if provider_code:
            stmt = stmt.where(AIChatLog.provider_code == provider_code)
        is_error = filters.get("is_error")
        if is_error is not None:
            stmt = stmt.where(AIChatLog.is_error == is_error)
        start_time = filters.get("start_time")
        if start_time:
            stmt = stmt.where(AIChatLog.created_at >= start_time)
        end_time = filters.get("end_time")
        if end_time:
            stmt = stmt.where(AIChatLog.created_at <= end_time)
        return stmt

    async def list_paginated(
        self, session: AsyncSession, offset: int, limit: int, **filters: Any
    ) -> list[AIChatLog]:
        stmt = (
            select(AIChatLog)
            .order_by(nullslast(AIChatLog.created_at.desc()))
            .offset(offset)
            .limit(limit)
        )
        stmt = self._apply_filters(stmt, **filters)
        result = await session.execute(stmt)
        return result.scalars().all()

    async def count(self, session: AsyncSession, **filters: Any) -> int:
        stmt = select(func.count()).select_from(AIChatLog)
        stmt = self._apply_filters(stmt, **filters)
        return await session.scalar(stmt) or 0

    async def delete_by_id(self, session: AsyncSession, log_id: str) -> bool:
        log = await self.get_by_id(session, log_id)
        if not log:
            return False
        await session.delete(log)
        await session.commit()
        return True


ai_chat_log_repository = AIChatLogRepository()
