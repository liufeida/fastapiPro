from fastapi import HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.exceptions import BusinessException
from app.core.security import (
    create_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from app.models.users import (
    PageResult,
    QueryRequest,
    UsersCreate,
    UsersLoginReo,
    UsersReo,
    UsersUpdate,
)
from app.repository.users import users_repository


class UsersServices:
    """用户服务层。"""

    async def authenticate_user(
        self, session: AsyncSession, username: str, password: str
    ) -> UsersLoginReo | None:
        """校验用户名与密码是否匹配。"""

        user = await users_repository.get_user_by_username(session, username)
        if not user:
            raise BusinessException(
                code=status.HTTP_400_BAD_REQUEST, message="账号或密码有误!!"
            )
        if not verify_password(password, user.hashed_password):
            raise BusinessException(
                code=status.HTTP_400_BAD_REQUEST, message="账号或密码有误!!"
            )
        return UsersLoginReo.model_validate(create_token(user))

    async def refresh(
        self, session: AsyncSession, refresh_token: str
    ) -> UsersLoginReo | None:
        user = await get_current_user(session=session, token=refresh_token)
        return UsersLoginReo.model_validate(create_token(user))

    async def get_user_by_id(
        self, session: AsyncSession, user_id: str
    ) -> UsersReo | None:
        db_user = await users_repository.get_user_by_id(session, user_id)
        return UsersReo.model_validate(db_user)

    async def create_user(self, session: AsyncSession, data: UsersCreate) -> UsersReo:
        user_dict = data.model_dump()

        # email 唯一性效验
        email = user_dict.get("email")
        if email:
            exists_user = await users_repository.get_user_by_email(session, email)
            if exists_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already exists",
                )

        if "password" in user_dict:
            user_dict["hashed_password"] = get_password_hash(user_dict.pop("password"))
        db_user = await users_repository.create_user(session, user_dict)
        return UsersReo.model_validate(db_user)

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

    async def update_user_infos(
        self, session: AsyncSession, user_id: str, data: UsersUpdate
    ) -> UsersReo:
        """更新用户资料，并处理唯一性校验与密码哈希。"""

        # 用户是否存在
        db_user = await users_repository.get_user_by_id(session, user_id)
        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        # update_data 字典
        update_data = data.model_dump(exclude_unset=True, exclude_none=True)
        if not update_data:
            return UsersReo.model_validate(db_user)

        # email 唯一性效验
        email = update_data.get("email")
        if email and email != db_user.email:
            exists_user = await users_repository.get_user_by_email(session, email)
            if exists_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already exists",
                )

        # 哈希密码
        if "password" in update_data:
            update_data["hashed_password"] = get_password_hash(
                update_data.pop("password")
            )

        # pydantic 数据库模型
        updated_user = await users_repository.update_user_infos(
            session,
            user_id,
            update_data,
        )

        # pydantic 响应模型
        return UsersReo.model_validate(updated_user)


users_services = UsersServices()
