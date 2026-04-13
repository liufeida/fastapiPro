from datetime import datetime
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

# from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler

app = FastAPI()


# 自定义异常类
class ItemException(Exception):
    def __init__(self, name: str):
        self.name = name


# 自定义异常处理器，处理这个异常的函数
@app.exception_handler(ItemException)
async def item_exception_handler(request: Request, exc: ItemException):
    return JSONResponse(
        status_code=418,
        content={"message": f"Oops! {exc.name} did something. There goes a rainbow..."},
    )


"""
raise

请求
  ↓
路由函数
  ↓
raise ItemException
  ↓
FastAPI 捕获异常
  ↓
找到 handler
  ↓
返回你定义的 JSON + 状态码
"""


@app.get("/items1/{name}")
async def items1(name: Annotated[str, Path(title="name")]):
    if name == "a":
        raise ItemException(name=name)
    return {"name": name}


# ----------------------------------------------------------------------------------
"""
无效数据
当你触发 HTTPException，或者请求中包含无效数据时，这些处理器负责返回默认的 JSON 响应,请求中包含无效数据时，FastAPI 内部会触发 RequestValidationError（底层 Pydantic）

fastapi 的 HTTPException & Starlette 的 HTTPException 是不同的，前者是后者的子类。
区别就是 fastapi 的 HTTPException 在 detail 字段中接受任意可以转换成 JSON 的数据，而 starlette 的 HTTPException 只能接受字符串。

误区：认为 raise HTTPException 也走 validation_exception_handler 函数？
答：访问 /item2/3 会触发 HTTPException，访问 /item2/a 会触发 RequestValidationError

RequestValidationError 触发时机（自动）：
- 参数类型错误
- 请求体效验错误
- Path /Query 不合法
在效验就已经触发了，所以不会进入路由函数，也就不会触发 HTTPException

如果在自定义之后，仍想用 FastAPI 默认的异常处理器，可以直接导入并使用：
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
return await request_validation_exception_handler(request, exc)

** HTTPException 控制返回，ValidationError 控制输入，Exception 兜底一切
"""


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc: StarletteHTTPException):
    print(f"StarletteHTTPException: {exc}")
    return PlainTextResponse(str(exc.detail), status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print(f"RequestValidationError: {exc}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )


@app.get("/items2/{item_id}")
async def items2(item_id: int):
    if item_id == 3:
        raise HTTPException(status_code=418, detail="Nope! I don't like 3.")
    return {"item_id": item_id}


"""
前端 JSON
   ↓
FastAPI 自动
   ↓
Pydantic对象（item）  ← 你现在拿到的是这个
   ↓
jsonable_encoder
   ↓
dict（纯JSON兼容）
"""


class Item(BaseModel):
    title: str
    timestamp: datetime
    description: str | None = None


fake_db = {}


@app.put("/items/{id}")
def update_item(id: str, item: Item):
    print(
        f"item: {item}"
    )  # item 不是 JSON，也不是 dict，而是一个 Python 对象（Pydantic 模型实例）
    json_compatible_item_data = jsonable_encoder(item)
    print(
        f"json_compatible_item_data: {json_compatible_item_data}"
    )  # 把 Python 对象 → 转成“可 JSON 序列化的 dict”
    fake_db[id] = json_compatible_item_data
    return fake_db
