from typing import Any

from sqlalchemy import or_
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.users import Users


class UsersRepository:
    """用户数据访问层。"""

    async def get_user_by_username(
        self, session: AsyncSession, username: str
    ) -> Users | None:
        """根据用户名查询单个用户。"""

        result = await session.execute(
            select(Users).where(Users.username == username, Users.is_deleted.is_(False))
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, session: AsyncSession, user_id: str) -> Users | None:
        result = await session.execute(
            select(Users).where(Users.id == user_id, Users.is_deleted.is_(False))
        )
        return result.scalar_one_or_none()

    def _apply_filters(self, stmt, **filters):
        """为查询语句统一追加筛选条件。"""

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
        """按条件查询用户分页数据。"""

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
        """统计符合条件的用户总数。"""

        stmt = select(func.count()).select_from(Users)
        stmt = self._apply_filters(stmt, **filters)
        return await session.scalar(stmt) or 0

    async def delete_user_by_id(
        self, session: AsyncSession, user_id: str
    ) -> Users | None:
        result = await session.execute(
            select(Users).where(Users.id == user_id, Users.is_deleted.is_(False))
        )
        user: Users = result.scalar_one_or_none()
        if user:
            user.is_deleted = True
            await session.commit()
        return user


users_repository = UsersRepository()
