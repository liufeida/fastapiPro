import asyncio
from typing import Annotated, AsyncIterable

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from app.api.dependencies import SessionDeep
from app.models.users import UsersLoginReo
from app.services.users import users_services

router = APIRouter()


@router.post("/login", response_model=UsersLoginReo, summary="用户登录")
async def login(
    session: SessionDeep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    login_info = await users_services.authenticate_user(
        session, form_data.username, form_data.password
    )
    return login_info


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
