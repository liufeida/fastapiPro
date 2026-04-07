from datetime import datetime, time, timedelta
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Body, FastAPI, Path, Query
from pydantic import AfterValidator, BaseModel, Field, HttpUrl


class SwaggerEnum(str, Enum):
    Query = "QueryValidation"
    Path = "PathValidation"
    Body = "BodyValidation"


app = FastAPI()


@app.get("/items", tags=[SwaggerEnum.Query])
async def read_items(
    q: Annotated[
        str | None, Query(min_length=2, max_length=11, pattern=r"^1[3-9]\d{9}$")
    ],
):
    results = {"items": [{"item_id": "Foo"}, {"item_id": "Bar"}]}
    if q:
        results.update({"q": q})
    return results


@app.get("/items2", tags=[SwaggerEnum.Query])
async def read_items2(q: Annotated[str | None, Query()]):
    return {"q": q}


# list[int] 会检查（并记录到文档）列表的内容必须是整数。但仅用 list 不会
@app.get("/items1", tags=[SwaggerEnum.Query])
async def read_items1(q: Annotated[list[str] | None, Query()] = None):
    return {"q": q}


@app.get("/items3", tags=[SwaggerEnum.Query])
async def read_items3(
    q: Annotated[
        list | None,
        Query(
            title="多选",
            description="传入一个列表",
            alias="q-list",
            deprecated=True,
            include_in_schema=False,
        ),
    ] = [],
    p: Annotated[str | None, Query()] = None,
):
    return {"q": q}


# 自定义效验
@app.get("/items4", tags=[SwaggerEnum.Query])
async def read_items4(
    q: Annotated[
        str | None,
        AfterValidator(lambda x: x.upper() if x else x),
    ],
):
    return {"q": q}


# -------------------------------- pydantic 参数模型 ------------------------------------------
# 使用 Pydantic 的 Field 在 Pydantic 模型内部声明校验和元数据
"""
仅仅进行这样的声明，你将通过 FastAPI 获得

1.对被嵌入的模型也适用的编辑器支持（自动补全等）
2.数据转换
3.数据校验
4.自动生成文档
"""


class Props(BaseModel):
    model_config = {"extra": "forbid"}
    limit: int = Field(100, gt=0, le=100)
    offset: int = Field(1, ge=1)
    order_by: Literal["created_at", "updated_at"] = "created_at"
    tags_list: list[str] = []
    tags_set: set[int] = Field(set({1, 2, 3}), min_items=1, max_items=10)
    tags_tuple: tuple[str, ...] = Field(("a",), min_items=1, max_items=10)
    tags_dict: dict[str, str | int | None] = Field({"a": 1}, min_items=1, max_items=10)


@app.get("/items5", tags=[SwaggerEnum.Query])
async def items5(props: Annotated[Props, Query()]):
    return props


@app.post("/items5_post", tags=[SwaggerEnum.Query])
async def items5_post(props: Annotated[Props, Body()]):
    return props


# -------------------------------- 请求体参数 ------------------------------------------
class Item(BaseModel):
    name: str
    description: str | None = None
    price: float
    tax: float | None = None
    title: str = Field(
        ..., title="标题", description="这是一个标题", example="Example Item"
    )


"""
embed = False
{
    "name": "Example Item",
    "description": "This is an example item.",
    "price": 9.99,
    "tax": 0.99
}

embed = True
{
    item: {
        "name": "Example Item",
        "description": "This is an example item.",
        "price": 9.99,
        "tax": 0.99
    }
}
"""


@app.post("/items6", tags=[SwaggerEnum.Body])
async def create_item(item: Annotated[Item, Body(embed=True)]):
    return item


# -------------------------------- 元数据，Schema ------------------------------------------
class ImageProps(BaseModel):
    model_config = {
        "json_schema_extra": {
            "example": {
                "url": "https://example.com/image.png",
                "name": "Example Image",
            }
        }
    }

    url: HttpUrl
    name: str


@app.post("/items7", tags=[SwaggerEnum.Body])
async def items7(
    image_list: Annotated[list[ImageProps], Body(embed=True, alias="image_list")],
):
    for image in image_list:
        print(image.url, image.name)
    return image_list


"""
*** JSON 键类型限制 ***
1. JSON 仅支持将 str 作为键
2. JSON 不支持将 int 作为键，因此在使用 dict[int, str] 时, FastAPI 会将 int 键转换为 str 键，并在文档中显示为 dict[str, str]。
3. 这种转换是为了确保与 JSON 格式的兼容性，因为 JSON 规范要求对象的键必须是字符串。
4. 实际上，我们接收的 dict 将具有 int 类型的键，但在文档中显示为 str 类型，以符合 JSON 的要求。
"""


@app.post("/items8", tags=[SwaggerEnum.Body])
async def items8(items: Annotated[dict[int, str], Body(embed=True)] = None):
    return items


# -------------------------------- 额外数据类型 ------------------------------------------
"""
uuid, time, date, datetime
"""


@app.put("/items9/{item_id}", tags=[SwaggerEnum.Body])
async def items9(
    item_id: Annotated[
        UUID, Path(title="id", description="92afcbd2-5c07-4868-abd8-526857f3c7ad")
    ],
    start_datetime: Annotated[datetime, Body()],
    end_datetime: Annotated[datetime, Body()],
    process_after: Annotated[timedelta, Body()],
    repeat_at: Annotated[time | None, Body()] = None,
):
    start_process = start_datetime + process_after
    duration = end_datetime - start_process
    return {
        "item_id": item_id,
        "start_datetime": start_datetime,
        "end_datetime": end_datetime,
        "process_after": process_after,
        "repeat_at": repeat_at,
        "start_process": start_process,
        "duration": duration,
    }
