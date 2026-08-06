from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.prompt import SystemPrompt


class PromptRepository:
    """系统提示词数据访问层。"""

    async def get_by_id(self, session: AsyncSession, prompt_id: str) -> SystemPrompt | None:
        """根据 id 查找一条未删除的提示词。"""
        result = await session.execute(
            select(SystemPrompt).where(
                SystemPrompt.id == prompt_id,
                SystemPrompt.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_prompt_code(self, session: AsyncSession, prompt_code: str) -> SystemPrompt | None:
        """根据 prompt_code 查找一条未删除的提示词。"""
        result = await session.execute(
            select(SystemPrompt).where(
                SystemPrompt.prompt_code == prompt_code,
                SystemPrompt.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def exists_by_prompt_code(
        self, session: AsyncSession, prompt_code: str, exclude_id: str | None = None
    ) -> bool:
        """检查 prompt_code 在未删除记录中是否已存在。

        exclude_id 用于更新时排除自身。
        """
        stmt = select(func.count()).select_from(SystemPrompt).where(
            SystemPrompt.prompt_code == prompt_code,
            SystemPrompt.is_deleted.is_(False),
        )
        if exclude_id:
            stmt = stmt.where(SystemPrompt.id != exclude_id)
        count = await session.scalar(stmt)
        return (count or 0) > 0

    async def get_enabled_by_model(
        self, session: AsyncSession, model_code: str
    ) -> list[SystemPrompt]:
        """查找 (model_code=指定 或 model_code is null) 中 is_enabled=True AND is_deleted=False 的所有提示词。

        按 sort_order asc, is_default desc 排序。
        """
        stmt = (
            select(SystemPrompt)
            .where(
                SystemPrompt.is_enabled.is_(True),
                SystemPrompt.is_deleted.is_(False),
                or_(
                    SystemPrompt.model_code == model_code,
                    SystemPrompt.model_code.is_(None),
                ),
            )
            .order_by(SystemPrompt.sort_order.asc(), SystemPrompt.is_default.desc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_global_default(self, session: AsyncSession) -> SystemPrompt | None:
        """查找 model_code is null AND is_enabled=True AND is_default=True AND is_deleted=False。"""
        result = await session.execute(
            select(SystemPrompt).where(
                SystemPrompt.model_code.is_(None),
                SystemPrompt.is_enabled.is_(True),
                SystemPrompt.is_default.is_(True),
                SystemPrompt.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, session: AsyncSession, data: dict) -> SystemPrompt:
        """创建一条提示词。"""
        db_prompt = SystemPrompt.model_validate(data)
        session.add(db_prompt)
        await session.commit()
        await session.refresh(db_prompt)
        return db_prompt

    async def update(
        self, session: AsyncSession, prompt_id: str, update_data: dict
    ) -> SystemPrompt | None:
        """根据 id 更新提示词字段。"""
        db_prompt = await self.get_by_id(session, prompt_id)
        if not db_prompt:
            return None
        for key, value in update_data.items():
            setattr(db_prompt, key, value)
        db_prompt.updated_at = datetime.now(timezone.utc)
        session.add(db_prompt)
        await session.commit()
        await session.refresh(db_prompt)
        return db_prompt

    async def soft_delete(
        self, session: AsyncSession, prompt_id: str
    ) -> SystemPrompt | None:
        """软删除一条提示词。"""
        db_prompt = await self.get_by_id(session, prompt_id)
        if not db_prompt:
            return None
        db_prompt.is_deleted = True
        db_prompt.updated_at = datetime.now(timezone.utc)
        session.add(db_prompt)
        await session.commit()
        await session.refresh(db_prompt)
        return db_prompt

    async def list_enabled(self, session: AsyncSession) -> list[SystemPrompt]:
        """查询所有启用的提示词（is_enabled=True AND is_deleted=False）。

        按 sort_order 升序、created_at 降序排列。
        """
        stmt = (
            select(SystemPrompt)
            .where(
                SystemPrompt.is_enabled.is_(True),
                SystemPrompt.is_deleted.is_(False),
            )
            .order_by(SystemPrompt.sort_order.asc(), SystemPrompt.created_at.desc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    def _apply_filters(self, stmt, **filters):
        """应用列表过滤条件。"""
        keyword = filters.get("keyword")
        if keyword:
            pattern = f"%{keyword}%"
            stmt = stmt.where(
                or_(
                    SystemPrompt.name.ilike(pattern),
                    SystemPrompt.prompt_code.ilike(pattern),
                    SystemPrompt.content.ilike(pattern),
                )
            )

        prompt_code = filters.get("prompt_code")
        if prompt_code:
            stmt = stmt.where(SystemPrompt.prompt_code == prompt_code)

        model_code = filters.get("model_code")
        if model_code:
            stmt = stmt.where(SystemPrompt.model_code == model_code)

        is_enabled = filters.get("is_enabled")
        if is_enabled is not None:
            stmt = stmt.where(SystemPrompt.is_enabled == is_enabled)

        return stmt

    async def list_paginated(
        self, session: AsyncSession, offset: int, limit: int, **filters: Any
    ) -> list[SystemPrompt]:
        """分页查询提示词列表。"""
        stmt = (
            select(SystemPrompt)
            .where(SystemPrompt.is_deleted.is_(False))
            .order_by(SystemPrompt.sort_order.asc(), SystemPrompt.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        stmt = self._apply_filters(stmt, **filters)
        result = await session.execute(stmt)
        return result.scalars().all()

    async def count(self, session: AsyncSession, **filters: Any) -> int:
        """统计符合过滤条件的提示词总数。"""
        stmt = (
            select(func.count())
            .select_from(SystemPrompt)
            .where(SystemPrompt.is_deleted.is_(False))
        )
        stmt = self._apply_filters(stmt, **filters)
        return await session.scalar(stmt) or 0

    async def clear_other_model_defaults(
        self, session: AsyncSession, model_code: str, exclude_id: str
    ) -> None:
        """将 model_code=指定 且 is_default=True 且 id!=exclude_id 的置为 False。"""
        stmt = (
            select(SystemPrompt)
            .where(
                SystemPrompt.model_code == model_code,
                SystemPrompt.is_default.is_(True),
                SystemPrompt.is_deleted.is_(False),
                SystemPrompt.id != exclude_id,
            )
        )
        result = await session.execute(stmt)
        others = result.scalars().all()
        for p in others:
            p.is_default = False
            p.updated_at = datetime.now(timezone.utc)
            session.add(p)
        if others:
            await session.commit()

    async def clear_global_default(
        self, session: AsyncSession, exclude_id: str
    ) -> None:
        """将 model_code is null 且 is_default=True 且 id!=exclude_id 的置为 False。"""
        stmt = (
            select(SystemPrompt)
            .where(
                SystemPrompt.model_code.is_(None),
                SystemPrompt.is_default.is_(True),
                SystemPrompt.is_deleted.is_(False),
                SystemPrompt.id != exclude_id,
            )
        )
        result = await session.execute(stmt)
        others = result.scalars().all()
        for p in others:
            p.is_default = False
            p.updated_at = datetime.now(timezone.utc)
            session.add(p)
        if others:
            await session.commit()


prompt_repository = PromptRepository()
