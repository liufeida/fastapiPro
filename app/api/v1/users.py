from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, Query
from fastapi.security import OAuth2PasswordRequestForm

from app.api.dependencies import SessionDeep
from app.core.security import get_current_active_user
from app.models.users import (
    PageResult,
    QueryRequest,
    Users,
    UsersCreate,
    UsersReo,
    UsersUpdate,
)
from app.services.users import users_services

router = APIRouter()


@router.post("/login", summary="用户登录")
async def login(
    session: SessionDeep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    login_info = await users_services.authenticate_user(
        session, form_data.username, form_data.password
    )
    return login_info


@router.get("/getCurrentUser", summary="获取当前登录用户", response_model=UsersReo)
async def read_user_me(
    current_user: Annotated[Users, Depends(get_current_active_user)],
):
    """返回当前登录用户信息。"""

    return current_user


@router.get(
    "/getUserById",
    response_model=Optional[UsersReo],
    summary="根据用户 id 获取用户信息",
)
async def get_user_by_id(session: SessionDeep, user_id: Annotated[str, Query()]):
    return await users_services.get_user_by_id(session, user_id)


@router.post(
    "/postUsersList",
    response_model=PageResult[UsersReo],
    summary="用户分页列表",
)
async def post_users_list(
    session: SessionDeep,
    query: Annotated[QueryRequest, Body()],
):
    """查询用户分页列表，支持分页、关键字模糊搜索和状态筛选。"""

    return await users_services.get_user_list_service(session, query)


@router.post("/postCreateUser", response_model=Optional[UsersReo], summary="创建用户")
async def create_user(session: SessionDeep, data: UsersCreate):
    """创建新用户，并对明文密码进行哈希处理。"""

    # 必须加 await，不加会把该协程对象当作返回值直接返回了
    db_user = await users_services.create_user(session, data)
    return db_user


@router.delete(
    "/deleteUserById", response_model=Optional[UsersReo], summary="根据用户 id 删除用户"
)
async def delete_user_by_id(session: SessionDeep, user_id: Annotated[str, Query()]):
    user = await users_services.delete_user_by_id(session, user_id)
    return user


@router.patch(
    "/updateUserInfos",
    response_model=UsersReo,
    summary="根据用户 id 更新用户信息",
)
async def update_user_infos(
    session: SessionDeep,
    user_id: Annotated[str, Query(description="用户 ID")],
    data: UsersUpdate,
):
    """按用户 ID 更新资料，支持局部更新和密码修改。"""

    return await users_services.update_user_infos(session, user_id, data)
