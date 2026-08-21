from fastapi import HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.exceptions import BusinessException
from app.core.security import (
    create_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from app.models.common import PageResult
from app.models.users import (
    QueryRequest,
    Users,
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
        return UsersLoginReo.model_validate(await create_token(user, session))

    async def refresh(
        self, session: AsyncSession, user: Users
    ) -> UsersLoginReo | None:
        return UsersLoginReo.model_validate(await create_token(user, session))

    async def google_login(
        self,
        session: AsyncSession,
        id_token: str | None = None,
        access_token: str | None = None,
    ) -> UsersLoginReo | None:
        """Google 账号登录。

        1. 验证 Google token（id_token 验签 / access_token 换 userinfo）
        2. 匹配用户，优先级：
           - 按 google_sub 匹配（Google 账号换邮箱也能识别）
           - 未命中再按 email 匹配，命中则把 google_sub 关联到该用户
           - 都没有则自动创建（密码存随机串哈希）
        3. 复用现有 create_token 签发 JWT，返回结构与 /auth/login 完全一致
        """
        from app.services.google_auth import (
            GoogleAuthError,
            get_google_userinfo,
            verify_google_id_token,
        )

        if not id_token and not access_token:
            raise BusinessException(
                code=status.HTTP_401_UNAUTHORIZED, message="Invalid Google token"
            )

        try:
            if id_token:
                info = await verify_google_id_token(id_token)
            else:
                info = await get_google_userinfo(access_token)
        except GoogleAuthError:
            raise BusinessException(
                code=status.HTTP_401_UNAUTHORIZED, message="Invalid Google token"
            )

        # 1) sub 优先匹配
        user = None
        if info.sub:
            user = await users_repository.get_user_by_google_sub(session, info.sub)

        # 2) email 兜底：命中则关联 google_sub（Google 已校验邮箱归属）
        if not user:
            email_user = await users_repository.get_user_by_email(session, info.email)
            if email_user:
                if info.sub and email_user.google_sub != info.sub:
                    email_user = await users_repository.update_user_infos(
                        session, email_user.id, {"google_sub": info.sub}
                    )
                user = email_user

        # 3) 都没有 → 自动创建
        if not user:
            user = await self._create_google_user(session, info)

        token_dict = await create_token(user, session)
        # Google 头像为外链 URL，直接覆盖 avatar_url（内部 avatar_id 关联的是上传文件）
        if info.picture:
            token_dict["avatar_url"] = info.picture
        return UsersLoginReo.model_validate(token_dict)

    async def _create_google_user(self, session: AsyncSession, info) -> Users:
        """自动创建 Google 登录用户，密码字段存随机串哈希（无法用密码登录）。"""
        import secrets

        from sqlalchemy.exc import IntegrityError

        username = await self._unique_username(session, info)
        user_dict = {
            "username": username,
            "full_name": info.name or "",
            "email": info.email,
            "phone": None,
            "hashed_password": get_password_hash(secrets.token_urlsafe(24)),
            "disabled": False,
            "is_deleted": False,
            "avatar_id": None,
            "google_sub": info.sub or None,
        }
        try:
            return await users_repository.create_user(session, user_dict)
        except IntegrityError:
            # 并发创建冲突：回滚后按 sub/email 回查一次，已存在则直接复用
            await session.rollback()
            existing = (
                await users_repository.get_user_by_google_sub(session, info.sub)
                if info.sub
                else None
            ) or await users_repository.get_user_by_email(session, info.email)
            if existing:
                return existing
            raise

    async def _unique_username(self, session: AsyncSession, info) -> str:
        """由 email 前缀/name 生成用户名，与已有用户冲突时追加随机后缀。"""
        import secrets

        base = (info.email or "").split("@")[0].strip() or (info.name or "").strip()
        if not base:
            base = "google_user"
        if not await users_repository.get_user_by_username(session, base):
            return base
        for _ in range(5):
            candidate = f"{base}_{secrets.token_hex(3)}"
            if not await users_repository.get_user_by_username(session, candidate):
                return candidate
        return f"{base}_{secrets.token_hex(6)}"

    async def get_user_by_id(
        self, session: AsyncSession, user_id: str
    ) -> UsersReo | None:
        db_user = await users_repository.get_user_by_id(session, user_id)
        if not db_user:
            return None

        user_dict = db_user.model_dump()

        if db_user.avatar_id:
            from app.models.files import File
            from sqlmodel import select

            result = await session.execute(
                select(File.url).where(File.id == db_user.avatar_id)
            )
            user_dict["avatar_url"] = result.scalar_one_or_none()
        else:
            user_dict["avatar_url"] = None

        return UsersReo.model_validate(user_dict)

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

        # 批量查询头像 URL
        avatar_ids = [u.avatar_id for u in users if u.avatar_id]
        avatar_urls = {}
        if avatar_ids:
            from app.models.files import File
            from sqlmodel import select

            result = await session.execute(
                select(File.id, File.url).where(File.id.in_(avatar_ids))
            )
            avatar_urls = {row.id: row.url for row in result.all()}

        # 组装返回数据
        records = []
        for user in users:
            user_dict = user.model_dump()
            # user_dict.pop("avatar_id", None)  # 移除 avatar_id，不传给前端
            user_dict["avatar_url"] = avatar_urls.get(user.avatar_id)
            records.append(UsersReo.model_validate(user_dict))

        return PageResult(
            records=records,
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
