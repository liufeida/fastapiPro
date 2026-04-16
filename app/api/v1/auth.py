from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.api.dependencies import SessionDeep
from app.models.users import UsersLoginReo
from app.services.users import users_services

router = APIRouter()


@router.post(
    "/login", response_model=UsersLoginReo, summary="用户登录", operation_id="login"
)
async def login(
    session: SessionDeep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    login_info = await users_services.authenticate_user(
        session, form_data.username, form_data.password
    )
    return login_info
