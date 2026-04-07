from typing import Annotated

from fastapi import FastAPI, File, Form, Response, UploadFile, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr

app = FastAPI()


class Item(BaseModel):
    name: str
    description: str | None = None
    price: float
    tax: float | None = None
    tags: list[str] = []


class Items1(BaseModel):
    name: str


@app.post("/items/")
async def create_item(item: Item) -> Item:
    return item


@app.get("/items/")
async def read_items() -> list[Item]:
    return [
        Item(name="Portal Gun", price=42.0),
        Item(name="Plumbus", price=32.0),
    ]


"""
(注): 装饰器的一个参数 response_model 可以用来指定响应数据的模型。它会将返回的数据转换为指定的模型，并且在文档中显示正确的响应模型。
1.路径操作装饰器参数 response_model
"""


@app.get("/items1/", response_model=list[Items1])
async def items1() -> any:
    return [
        Item(name="Portal Gun", price=42.0),
        Item(name="Plumbus", price=32.0),
    ]


"""
class Items2(BaseModel):
    name: str
    password: str
    email: EmailStr
    full_name: str | None = None


class Items2_extend(BaseModel):
    name: str
    email: EmailStr
    full_name: str = None

"""


# class 继承
class Items2(BaseModel):
    name: str
    email: EmailStr
    full_name: str | None = None


class Items2_extend(Items2):
    password: str


@app.post("/items2", response_model=Items2)
async def items2(userInfos: Items2_extend) -> any:
    return userInfos


"""
想要 FastAPI 执行默认的数据校验、文档、过滤等, response_model=None 禁用响应模型
"""


@app.get("/items3", response_model=None)
async def items3(bool: bool) -> Response | dict:
    if bool:
        return RedirectResponse(url="https://announcement.ibox.art/#/bulletin")
    return JSONResponse(content={"message": "Hello World"})


@app.post("/items4/", status_code=201)
async def items4(name: str):
    return {"name": name}


@app.post("/items5/", status_code=status.HTTP_201_CREATED)
async def items5(name: str):
    return {"name": name}


"""
"""


@app.post("/items6")
async def items6(username: Annotated[str, Form()], password: Annotated[str, Form()]):
    return {"username": username, "password": password}


"""
"""


@app.post("/files")
async def files(file: Annotated[bytes, File()]):
    return {"file_size": len(file)}


@app.post("/uploadfile")
async def uploadFile(file: UploadFile):
    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "file_size": len(await file.read()),
    }


@app.post("/uploadfiles/")
async def uploadFiles(
    # files: Annotated[list[UploadFile], File(description="多文件上传")],
    files: list[UploadFile] = File(...),
):
    return {"files": [file.filename for file in files]}
