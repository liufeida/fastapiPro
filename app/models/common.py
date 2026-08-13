
from typing import Generic, List, TypeVar

from pydantic import BaseModel
from pydantic import Field as PydanticField
from pydantic import field_validator
from sqlmodel import  Field

T = TypeVar("T")

class PageParams(BaseModel):
    """通用分页参数。"""

    page: int = Field(default=1, ge=1, description="页码，从 1 开始")
    pageSize: int = PydanticField(
        default=10,
        ge=1,
        le=100,
        description="每页条数，默认 10，最大 100",
    )

    @property
    def offset(self) -> int:
        """将页码转换为数据库 offset。"""

        return (self.page - 1) * self.pageSize

    @property
    def limit(self) -> int:
        """将分页大小转换为数据库 limit。"""

        return self.pageSize

class PageResult(BaseModel, Generic[T]):
    """通用分页返回结构。"""

    records: List[T]
    total: int
    page: int
    pageSize: int
    pages: int
