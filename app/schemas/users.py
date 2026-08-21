# 用于令牌端点响应的 Pydantic 模型

from pydantic import BaseModel


class LoginModel(BaseModel):
    username: str
    password: str


class GoogleLoginModel(BaseModel):
    """Google 登录请求体。

    - id_token：Google 登录返回的 JWT（推荐，后端验签更安全）
    - access_token：可选，部分场景传 Google access_token，后端调 userinfo 换信息
    """

    id_token: str | None = None
    access_token: str | None = None


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


class User(BaseModel):
    username: str
    email: str | None = None
    full_name: str | None = None
    disabled: bool | None = None


class UserInDB(User):
    hashed_password: str
