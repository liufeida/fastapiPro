from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.api.dependencies import SessionDeep
from app.core.exceptions import Execute
from app.models.users import UsersLoginReo
from app.schemas.exceptions import ResponseModel
from app.schemas.users import GoogleLoginModel, LoginModel
from app.services.users import users_services

router = APIRouter()


@router.post(
    "/fastapi_login",
    response_model=UsersLoginReo,
    summary="用户登录",
    operation_id="fastapi_login",
    include_in_schema=False,
)
async def fastapi_login(
    session: SessionDeep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    # form_data: Annotated[Login, Body()],
):
    login_info = await users_services.authenticate_user(
        session, form_data.username, form_data.password
    )
    return login_info


@router.post(
    "/login",
    response_model=ResponseModel[UsersLoginReo],
    summary="用户登录",
    operation_id="login",
)
async def login(
    session: SessionDeep,
    form_data: Annotated[LoginModel, Body()],
):
    login_info = await users_services.authenticate_user(
        session, form_data.username, form_data.password
    )
    return Execute.response(login_info)


@router.post(
    "/google",
    response_model=ResponseModel[UsersLoginReo],
    summary="Google 账号登录",
    operation_id="google_login",
)
async def google_login(
    session: SessionDeep,
    body: Annotated[GoogleLoginModel, Body()],
):
    """Google 账号登录：验证 id_token/access_token，按 email 匹配或自动创建用户，签发 JWT。"""
    data = await users_services.google_login(
        session, id_token=body.id_token, access_token=body.access_token
    )
    return Execute.response(data)
