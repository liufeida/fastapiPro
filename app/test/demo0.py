from enum import Enum

from fastapi import FastAPI
from pydantic import BaseModel


# 定义一个枚举类ItemEnum，包含三个成员：electronics、clothing和books。这些成员可以用来限制API路径参数的值，确保它们只能是这三个选项之一。
class ItemEnum(str, Enum):
    electronics = "electronics"
    clothing = "clothing"
    books = "books"


class ItemProps(BaseModel):
    name: str
    description: str | None = None
    price: float
    tax: float | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Example Item",
                "description": "This is an example item.",
                "price": 9.99,
                "tax": 0.99,
            }
        }
    }


# 创建一个FastAPI应用实例
app = FastAPI(
    version="2.0.0",
)


# 根路径 - 当访问根路径时，FastAPI会返回一个简单的JSON响应{"Hello": "World"}。
@app.get("/", tags=["Root"])
def read_root():
    return {"Hello": "World"}


"""
1. 路径参数
users/{user_id} - user_id参数是一个字符串类型，FastAPI会将路径中的值作为字符串传递给函数。
路径参数都是必填的，必须在URL中提供相应的值，否则FastAPI会返回一个错误响应。
"""


@app.get("/users/{user_id}", tags=["Path"])
async def read_user(user_id: str):
    return {"user_id": user_id}


# models/{model_name} - model_name参数是一个枚举类型，FastAPI会自动验证传入的值是否在枚举中定义，并将其转换为相应的枚举成员。
@app.get("/models/{model_name}", tags=["Enum"])
async def read_model(model_name: ItemEnum):
    if model_name == ItemEnum.electronics:
        a = 1
    elif model_name == ItemEnum.clothing:
        a = 2
    else:
        a = 3
    return {"model_name": a}


# files/{file_path:path} - path参数可以匹配路径中的斜杠，因此可以捕获整个路径作为参数值。
@app.get("/files/{file_path:path}", tags=["Path"])
async def read_file(file_path: str):
    return {"file_path": file_path}


"""
2. 查询参数
查询参数是URL中以?分隔的键值对，通常用于过滤、排序或分页等操作。
"""


# items/{item_id} - item_id参数是一个整数类型，FastAPI会将路径中的值转换为整数并传递给函数。
# 还定义了两个查询参数p和q，p是一个字符串类型，默认值为"default"，q是一个可声明可选的查询参数。
@app.get("/api/{item_id}", tags=["Query"])
def read_item(item_id: int, p: str = "default", q: int | None = None):
    return {"item_id": item_id, "p": p, "q": q}


# items?skip=1&limit=10，skip,limit 是查询参数
@app.get("/items", tags=["Query"])
def read_items(skip: int = 0, limit: int = 10):
    fake_items_db = [{"item_name": "Foo"}, {"item_name": "Bar"}, {"item_name": "Baz"}]
    return fake_items_db[skip : skip + limit]


"""
【tip】
1. 识别同时声明的多个路径参数和查询参数,而且声明查询参数的顺序并不重要
2. 路径参数本身就是必填的
3. 查询参数可选,提供默认值,None或者其他; 如果没有提供默认值,则该查询参数为必填项
4. py 的参数顺序规则：有默认值的参数后面不能跟着没有默认值的参数, 比如 user_id: str = None, q: str 这种写法是错误的, 因为 q 没有默认值, 但是 user_id 有默认值
"""


@app.get("/items/{item_id}/user/{user_id}", tags=["Query"])
async def update_item(item_id: str, user_id: str, q: str, short: bool = False):
    item = {"item_id": item_id, "user_id": user_id}
    if q:
        item.update({"q": q})
    if not short:
        item.update(
            {"description": "This is an amazing item that has a long description"}
        )
    return item


"""
3. 请求体
请求体通常用于POST、PUT、PATCH等HTTP方法，用于发送数据到服务器。
与声明查询参数一样，包含默认值的模型属性是可选的，否则就是必选的
"""


@app.post("/items", tags=["Body"])
async def create_item(item: ItemProps):
    return item


"""
FastAPI 能识别与路径参数匹配的函数参数应该从路径中获取，而声明为 Pydantic 模型的函数参数应该从请求体中获取

按照如下规则进行识别
1. 函数参数如果是一个路径参数, 那么它会被识别为一个路径参数
2. 函数参数如果是一个 Pydantic 模型, 那么它会被识别为一个请求体参数
3. 函数参数如果既不是路径参数也不是 Pydantic 模型, 那么它会被识别为一个查询参数
"""


@app.put("/items/{item_id}")
async def put_item(item_id: int, item: ItemProps, q: str | None = None):
    result = {"item_id": item_id, **item.model_dump()}
    if q:
        result.update({"q": q})
    return result


def main():
    print("Hello from fastapi-demo!")


if __name__ == "__main__":
    main()
