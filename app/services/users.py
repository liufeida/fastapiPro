from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.security import verify_password
from app.models.users import PageResult, QueryRequest, UsersReo
from app.repository.users import users_repository


class UsersServices:
    """用户服务层。"""

    async def authenticate_user(
        self, session: AsyncSession, username: str, password: str
    ):
        """校验用户名与密码是否匹配。"""

        user = await users_repository.get_user_by_username(session, username)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    async def get_user_by_id(self, session: AsyncSession, user_id: str):
        return await users_repository.get_user_by_id(session, user_id)

    async def get_user_list_service(
        self, session: AsyncSession, query: QueryRequest
    ) -> PageResult[UsersReo]:
        """获取用户分页列表，并统一封装分页返回结果。"""

        filters = query.to_repository_filters()

        users = await users_repository.get_users_by_offset_limit(
            session,
            offset=query.offset,
            limit=query.limit,
            **filters,
        )
        total = await users_repository.count_users(session, **filters)
        pages = (total + query.pageSize - 1) // query.pageSize if total > 0 else 0

        return PageResult(
            data=[UsersReo.model_validate(user) for user in users],
            total=total,
            page=query.page,
            pageSize=query.pageSize,
            pages=pages,
        )

    async def delete_user_by_id(self, session: AsyncSession, user_id: str) -> UsersReo:
        user = await users_repository.delete_user_by_id(session, user_id)
        return user


users_services = UsersServices()
