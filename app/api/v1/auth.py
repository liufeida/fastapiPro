import asyncio
from typing import AsyncIterable

from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

router = APIRouter()


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
