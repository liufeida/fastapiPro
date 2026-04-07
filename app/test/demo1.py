from typing import Annotated

from fastapi import FastAPI, Path, Query

app = FastAPI()


@app.get("/items1/{item_id}")
async def items1(
    item_id: Annotated[int, Path(title="id")],
    q: Annotated[str | None, Query(title="查询参数")] = None,
):
    result = {"item_id": item_id}
    if q:
        result.update({"q": q})
    return result


@app.get("/items2/{item_id}")
async def items2(
    q: str,
    item_id: Annotated[int, Path(title="id")],
):
    result = {"item_id": item_id}
    if q:
        result.update({"q": q})
    return result


# 数值校验
"""
int , float 都适用

ge 大于等于
le 小于等于
gt 大于
lt 小于
"""


@app.get("/item3/{item_id}")
async def item3(item_id: Annotated[int, Path(title="id", ge=1, le=10)]):
    return {"item_id": item_id}
