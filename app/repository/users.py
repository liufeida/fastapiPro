from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.users import Users


class UsersRepository:
    """Users data access layer."""

    async def get_user_by_username(
        self, session: AsyncSession, username: str
    ) -> Users | None:
        """Find one active user by username."""

        result = await session.execute(
            select(Users).where(Users.username == username, Users.is_deleted.is_(False))
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, session: AsyncSession, user_id: str) -> Users | None:
        """Find one active user by id."""

        result = await session.execute(
            select(Users).where(Users.id == user_id, Users.is_deleted.is_(False))
        )
        return result.scalar_one_or_none()

    async def get_user_by_email(
        self, session: AsyncSession, email: str
    ) -> Users | None:
        """Find one active user by email."""

        result = await session.execute(
            select(Users).where(Users.email == email, Users.is_deleted.is_(False))
        )
        return result.scalar_one_or_none()

    async def create_user(
        self, session: AsyncSession, data: dict[str, any]
    ) -> Users | None:
        # 将字典效验转化为 pydantic 模型
        db_user = Users.model_validate(
            data
        )  # 有验证，中性能，多余字段报错，适用于外部输入要严格效验的
        # db_user = Users(**data) # 无验证，快性能，多余字段会忽略，适用于内部可靠数据不要验证的
        session.add(db_user)
        await session.commit()
        await session.refresh(db_user)
        return db_user

    def _apply_filters(self, stmt, **filters):
        """Apply common list filters to a statement."""

        keyword = filters.get("keyword")
        if keyword:
            pattern = f"%{keyword}%"
            stmt = stmt.where(
                or_(
                    Users.username.ilike(pattern),
                    Users.full_name.ilike(pattern),
                    Users.email.ilike(pattern),
                )
            )

        for key, value in filters.items():
            if value is None or key == "keyword":
                continue

            if key.endswith("_like"):
                field_name = key[:-5]
                if hasattr(Users, field_name):
                    stmt = stmt.where(getattr(Users, field_name).ilike(f"%{value}%"))
                continue

            if hasattr(Users, key):
                stmt = stmt.where(getattr(Users, key) == value)

        return stmt

    async def get_users_by_offset_limit(
        self, session: AsyncSession, offset: int, limit: int, **filters: Any
    ) -> list[Users]:
        """Query paginated active users."""

        stmt = (
            select(Users)
            .where(Users.is_deleted.is_(False))
            .order_by(Users.username)
            .offset(offset)
            .limit(limit)
        )
        stmt = self._apply_filters(stmt, **filters)
        result = await session.execute(stmt)
        return result.scalars().all()

    async def count_users(self, session: AsyncSession, **filters: Any) -> int:
        """Count active users that match the filters."""

        stmt = (
            select(func.count()).select_from(Users).where(Users.is_deleted.is_(False))
        )
        stmt = self._apply_filters(stmt, **filters)
        return await session.scalar(stmt) or 0

    async def delete_user_by_id(
        self, session: AsyncSession, user_id: str
    ) -> Users | None:
        """Soft delete a user by id."""

        user = await self.get_user_by_id(session, user_id)
        if user:
            user.is_deleted = True
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user

    async def update_user_infos(
        self, session: AsyncSession, user_id: str, update_data: dict[str, Any]
    ) -> Users | None:
        """Update user fields by id."""

        db_user = await self.get_user_by_id(session, user_id)

        for key, value in update_data.items():
            setattr(db_user, key, value)

        db_user.updated_at = datetime.now(timezone.utc)

        session.add(db_user)
        await session.commit()
        await session.refresh(db_user)
        return db_user


users_repository = UsersRepository()
