from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI()

items = {1, 2, 3, 4, 5}


@app.get("/items/{item_id}", summary="获取 item")
async def items1(item_id: int) -> dict[str, int]:

    if item_id not in items:
        raise HTTPException(status_code=418, detail="id 不在列表内")
    return {"item_id": item_id}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    return PlainTextResponse("field" + str(exc.detail), status_code=exc.status_code)


# @app.exception_handler(RequestValidationError)
# async def validation_exception_handler(request, exc: RequestValidationError):
#     message = "请求参数错误"
#     for error in exc.errors():
#         message += f"Field: {error['loc']}: Error: {error['msg']}; "
#     return PlainTextResponse(message, status_code=400)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    message = "请求参数错误"
    for error in exc.errors():
        message += f"Field: {error['loc']}: Error: {error['msg']}; "
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({"detail": exc.errors(), "body": exc.body}),
    )


class Item(BaseModel):
    title: str
    size: int


@app.post("/items/", summary="创建一个 item")
async def create_item(item: Item):
    """
      Create an item with all the information:

    - **name**: each item must have a name
    - **description**: a long description
    - **price**: required
    - **tax**: if the item doesn't have tax, you can omit this
    - **tags**: a set of unique tag strings for this item
    """
    return item


@app.post("/items_deprecated/", summary="创建一个 item", deprecated=True)
async def create_item_deprecated(item: Item):
    """
      Create an item with all the information:

    - **name**: each item must have a name
    - **description**: a long description
    - **price**: required
    - **tax**: if the item doesn't have tax, you can omit this
    - **tags**: a set of unique tag strings for this item
    """
    return item
