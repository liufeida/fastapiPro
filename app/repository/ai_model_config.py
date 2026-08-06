from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.ai_model_config import AIModelConfig


class AIModelConfigRepository:
    """AI 模型配置数据访问层。"""

    async def get_by_id(self, session: AsyncSession, config_id: str) -> AIModelConfig | None:
        """根据 id 查找一条未删除的配置。"""
        result = await session.execute(
            select(AIModelConfig).where(
                AIModelConfig.id == config_id,
                AIModelConfig.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_model_code(self, session: AsyncSession, model_code: str) -> AIModelConfig | None:
        """根据 model_code 查找一条未删除的配置（路由调度用）。"""
        result = await session.execute(
            select(AIModelConfig).where(
                AIModelConfig.model_code == model_code,
                AIModelConfig.is_deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def exists_by_provider_and_code(
        self, session: AsyncSession, provider_code: str, model_code: str, exclude_id: str | None = None
    ) -> bool:
        """检查 (provider_code, model_code) 在未删除记录中是否已存在。

        exclude_id 用于更新时排除自身。
        """
        stmt = select(func.count()).select_from(AIModelConfig).where(
            AIModelConfig.provider_code == provider_code,
            AIModelConfig.model_code == model_code,
            AIModelConfig.is_deleted.is_(False),
        )
        if exclude_id:
            stmt = stmt.where(AIModelConfig.id != exclude_id)
        count = await session.scalar(stmt)
        return (count or 0) > 0

    async def create(self, session: AsyncSession, data: dict) -> AIModelConfig:
        """创建一条配置。"""
        db_config = AIModelConfig.model_validate(data)
        session.add(db_config)
        await session.commit()
        await session.refresh(db_config)
        return db_config

    async def update(self, session: AsyncSession, config_id: str, update_data: dict) -> AIModelConfig | None:
        """根据 id 更新配置字段。"""
        db_config = await self.get_by_id(session, config_id)
        if not db_config:
            return None
        for key, value in update_data.items():
            setattr(db_config, key, value)
        db_config.updated_at = datetime.now(timezone.utc)
        session.add(db_config)
        await session.commit()
        await session.refresh(db_config)
        return db_config

    async def soft_delete(self, session: AsyncSession, config_id: str) -> AIModelConfig | None:
        """软删除一条配置。"""
        db_config = await self.get_by_id(session, config_id)
        if not db_config:
            return None
        db_config.is_deleted = True
        db_config.updated_at = datetime.now(timezone.utc)
        session.add(db_config)
        await session.commit()
        await session.refresh(db_config)
        return db_config

    async def list_enabled(self, session: AsyncSession) -> list[AIModelConfig]:
        """查询所有启用的配置（is_enabled=True AND is_deleted=False）。

        按 sort_order 升序、created_at 降序排列。
        """
        stmt = (
            select(AIModelConfig)
            .where(
                AIModelConfig.is_enabled.is_(True),
                AIModelConfig.is_deleted.is_(False),
            )
            .order_by(AIModelConfig.sort_order.asc(), AIModelConfig.created_at.desc())
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    def _apply_filters(self, stmt, **filters):
        """应用列表过滤条件（参考 UsersRepository._apply_filters）。"""
        keyword = filters.get("keyword")
        if keyword:
            pattern = f"%{keyword}%"
            stmt = stmt.where(
                or_(
                    AIModelConfig.model_code.ilike(pattern),
                    AIModelConfig.model_name.ilike(pattern),
                    AIModelConfig.provider_code.ilike(pattern),
                )
            )

        provider_code = filters.get("provider_code")
        if provider_code:
            stmt = stmt.where(AIModelConfig.provider_code == provider_code)

        is_enabled = filters.get("is_enabled")
        if is_enabled is not None:
            stmt = stmt.where(AIModelConfig.is_enabled == is_enabled)

        return stmt

    async def list_paginated(
        self, session: AsyncSession, offset: int, limit: int, **filters: Any
    ) -> list[AIModelConfig]:
        """分页查询配置列表。"""
        stmt = (
            select(AIModelConfig)
            .where(AIModelConfig.is_deleted.is_(False))
            .order_by(AIModelConfig.sort_order.asc(), AIModelConfig.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        stmt = self._apply_filters(stmt, **filters)
        result = await session.execute(stmt)
        return result.scalars().all()

    async def count(self, session: AsyncSession, **filters: Any) -> int:
        """统计符合过滤条件的配置总数。"""
        stmt = (
            select(func.count())
            .select_from(AIModelConfig)
            .where(AIModelConfig.is_deleted.is_(False))
        )
        stmt = self._apply_filters(stmt, **filters)
        return await session.scalar(stmt) or 0

    async def clear_other_defaults(self, session: AsyncSession, exclude_id: str) -> None:
        """将除 exclude_id 外的所有未删除记录的 is_default 置为 False（默认模型互斥）。"""
        stmt = (
            select(AIModelConfig)
            .where(
                AIModelConfig.is_default.is_(True),
                AIModelConfig.is_deleted.is_(False),
                AIModelConfig.id != exclude_id,
            )
        )
        result = await session.execute(stmt)
        others = result.scalars().all()
        for cfg in others:
            cfg.is_default = False
            cfg.updated_at = datetime.now(timezone.utc)
            session.add(cfg)
        if others:
            await session.commit()


ai_model_config_repository = AIModelConfigRepository()
