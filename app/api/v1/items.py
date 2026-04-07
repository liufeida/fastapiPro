from typing import Annotated

from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/items")
async def items(token: Annotated[str, Query()]):
    return {"token": token}
