from datetime import datetime, timezone
from typing import Any

from sqlalchemy import insert, nullslast, or_
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.api_access_log import ApiAccessLog


class ApiAccessLogRepository:
    """HTTP API 访问日志数据访问层。"""

    async def create_batch(self, session: AsyncSession, records: list[dict]) -> None:
        """批量插入日志记录。

        使用 INSERT INTO ... VALUES (...), (...) 单条 SQL，避免 N 次 round-trip。
        """
        if not records:
            return
        stmt = insert(ApiAccessLog).values(records)
        await session.execute(stmt)
        await session.commit()

    async def get_by_id(self, session: AsyncSession, log_id: str) -> ApiAccessLog | None:
        result = await session.execute(select(ApiAccessLog).where(ApiAccessLog.id == log_id))
        return result.scalar_one_or_none()

    def _apply_filters(self, stmt, **filters: Any):
        trace_id = filters.get("trace_id")
        if trace_id:
            stmt = stmt.where(ApiAccessLog.trace_id == trace_id)
        path_keyword = filters.get("path_keyword")
        if path_keyword:
            stmt = stmt.where(ApiAccessLog.path.ilike(f"%{path_keyword}%"))
        method = filters.get("method")
        if method:
            stmt = stmt.where(ApiAccessLog.method == method)
        response_status = filters.get("response_status")
        if response_status is not None:
            stmt = stmt.where(ApiAccessLog.response_status == response_status)
        is_error = filters.get("is_error")
        if is_error is not None:
            stmt = stmt.where(ApiAccessLog.is_error == is_error)
        start_time = filters.get("start_time")
        if start_time:
            stmt = stmt.where(ApiAccessLog.created_at >= start_time)
        end_time = filters.get("end_time")
        if end_time:
            stmt = stmt.where(ApiAccessLog.created_at <= end_time)
        return stmt

    async def list_paginated(
        self, session: AsyncSession, offset: int, limit: int, **filters: Any
    ) -> list[ApiAccessLog]:
        stmt = (
            select(ApiAccessLog)
            .order_by(nullslast(ApiAccessLog.created_at.desc()))
            .offset(offset)
            .limit(limit)
        )
        stmt = self._apply_filters(stmt, **filters)
        result = await session.execute(stmt)
        return result.scalars().all()

    async def count(self, session: AsyncSession, **filters: Any) -> int:
        stmt = select(func.count()).select_from(ApiAccessLog)
        stmt = self._apply_filters(stmt, **filters)
        return await session.scalar(stmt) or 0

    async def delete_by_id(self, session: AsyncSession, log_id: str) -> bool:
        log = await self.get_by_id(session, log_id)
        if not log:
            return False
        await session.delete(log)
        await session.commit()
        return True


api_access_log_repository = ApiAccessLogRepository()
