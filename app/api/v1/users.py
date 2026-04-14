from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query

from app.api.dependencies import SessionDeep
from app.core.exceptions import Execute
from app.core.security import get_current_active_user
from app.models.users import (
    PageResult,
    QueryRequest,
    Users,
    UsersCreate,
    UsersLoginReo,
    UsersReo,
    UsersUpdate,
)
from app.schemas.exceptions import ResponseModel
from app.services.users import users_services

router = APIRouter()


@router.post(
    "/refresh",
    response_model=ResponseModel[UsersLoginReo],
    summary="刷新获取 access_token",
)
async def refresh(
    session: SessionDeep,
    refresh_token: str,
):
    data = await users_services.refresh(session, refresh_token)
    return Execute.response(data)


@router.get(
    "/getCurrentUser",
    summary="获取当前登录用户",
    response_model=ResponseModel[UsersReo],
)
async def read_user_me(
    data: Annotated[Users, Depends(get_current_active_user)],
):
    """返回当前登录用户信息。"""

    return Execute.response(data)


@router.get(
    "/getUserById",
    response_model=ResponseModel[UsersReo],
    summary="根据用户 id 获取用户信息",
)
async def get_user_by_id(session: SessionDeep, user_id: Annotated[str, Query()]):
    data = await users_services.get_user_by_id(session, user_id)
    return Execute.response(data)


@router.post(
    "/postUsersList",
    response_model=ResponseModel[PageResult[UsersReo]],
    summary="用户分页列表",
)
async def post_users_list(
    session: SessionDeep,
    query: Annotated[QueryRequest, Body()],
):
    """查询用户分页列表，支持分页、关键字模糊搜索和状态筛选。"""

    data = await users_services.get_user_list_service(session, query)
    return Execute.response(data)


@router.post(
    "/postCreateUser", response_model=ResponseModel[UsersReo], summary="创建用户"
)
async def create_user(session: SessionDeep, data: UsersCreate):
    """创建新用户，并对明文密码进行哈希处理。"""

    # 必须加 await，不加会把该协程对象当作返回值直接返回了
    data = await users_services.create_user(session, data)
    return Execute.response(data)


@router.delete(
    "/deleteUserById",
    response_model=ResponseModel[UsersReo],
    summary="根据用户 id 删除用户",
)
async def delete_user_by_id(session: SessionDeep, user_id: Annotated[str, Query()]):
    data = await users_services.delete_user_by_id(session, user_id)
    return Execute.response(data)


@router.patch(
    "/updateUserInfos",
    response_model=ResponseModel[UsersReo],
    summary="根据用户 id 更新用户信息",
)
async def update_user_infos(
    session: SessionDeep,
    user_id: Annotated[str, Query(description="用户 ID")],
    data: UsersUpdate,
):
    """按用户 ID 更新资料，支持局部更新和密码修改。"""

    data = await users_services.update_user_infos(session, user_id, data)
    return Execute.response(data)
