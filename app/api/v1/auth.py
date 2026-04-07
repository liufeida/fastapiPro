import asyncio
from datetime import timedelta
from typing import Annotated, AsyncIterable

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from app.api.dependencies import SessionDeep
from app.core.security import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token
from app.schemas.users import Token
from app.services.users import users_services

router = APIRouter()


@router.post("/login", summary="用户登录")
async def login(
    session: SessionDeep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    user = await users_services.authenticate_user(
        session, form_data.username, form_data.password
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires,
    )
    return Token(access_token=access_token, token_type="bearer")


class Item(BaseModel):
    name: str
    price: float


items1 = [
    Item(name="Plumbus", price=32.99),
    Item(name="Portal Gun", price=999.99),
    Item(name="Meeseeks Box", price=49.99),
]


@router.get("/items/stream", response_class=EventSourceResponse)
async def stream_items() -> AsyncIterable[ServerSentEvent]:
    yield ServerSentEvent(comment="stream of item updates")
    for i, item in enumerate(items1):
        await asyncio.sleep(1)
        yield ServerSentEvent(data=item, event="item_update", id=str(i + 1), retry=5000)
