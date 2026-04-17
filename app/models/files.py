import uuid
from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import ConfigDict
from sqlmodel import Column, DateTime, Field, SQLModel


class FileBase(SQLModel):
    """文件元数据基类."""

    url: str
    filename: str
    file_path: str
    file_size: int
    content_type: str


class File(FileBase, table=True):
    """用于存储上传文件元数据的数据库表."""

    __tablename__ = "file"
    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True)),
        default_factory=lambda: datetime.now(timezone.utc),
    )


class FileCreate(FileBase):
    """用于保存文件元数据时所使用的数据包."""


class FileOut(FileBase):
    """上传文件的 API 响应模型."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class PageParams(SQLModel):
    """通用分页参数。"""

    page: int = Field(default=1, ge=1, description="页码，从 1 开始")
    pageSize: int = Field(
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


class QueryRequest(PageParams):
    """用户分页列表查询参数。"""

    ids: list[str] | None = Field(
        default=None,
        description="ids 查询",
    )


T = TypeVar("T")


class PageResult(SQLModel, Generic[T]):
    """通用分页返回结构。"""

    records: list[T]
    total: int
    page: int
    pageSize: int
    pages: int
