from typing import Annotated

from fastapi import Depends, FastAPI

app = FastAPI()

"""
👉 在 FastAPI 中：

依赖注入是一种机制，用于在请求处理前自动解析并执行依赖项，并将其返回值注入到路径操作函数的参数中，从而实现解耦、复用和自动化管理。

帮你提前执行一段逻辑，并把结果塞进函数参数里

不要把 FastAPI 的 Depends 当成“完整版 DI”, 一个轻量级、函数式的依赖注入实现

👉 思想一样：解耦、复用、交给框架管理
👉 实现不同：FastAPI 是函数调用，Spring 是容器管理
"""


class Common:
    def __init__(self, q: str, skip: int = 0, limit: int = 100):
        self.q = q
        self.skip = skip
        self.limit = limit

    def demo(self):
        print("This is a demo method in Common class.")


CommonDependency = Annotated[Common, Depends()]


db = [{"item_id": "Foo"}, {"item_id": "Bar"}, {"item_id": "Baz"}]


@app.get("/items/")
async def items(common: CommonDependency):
    response = {}
    if common.q:
        common.demo()
        response.update({"q": common.q})
    items = db[common.skip : common.skip + common.limit]
    response.update({"items": items})
    return response
