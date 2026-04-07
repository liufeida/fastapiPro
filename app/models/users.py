import uuid
from datetime import datetime, timezone
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField
from pydantic import field_validator
from sqlmodel import Column, DateTime, Field, SQLModel


class UsersBase(SQLModel):
    """用户基础字段。"""

    username: str
    full_name: str | None = ""
    email: str
    disabled: bool = False
    is_deleted: bool = False
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True)),
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True)),
        default_factory=lambda: datetime.now(timezone.utc),
    )


class Users(UsersBase, table=True):
    """用户表模型。"""

    id: Optional[str] = Field(
        default_factory=lambda: uuid.uuid4().hex, primary_key=True
    )
    hashed_password: str


class UsersCreate(UsersBase):
    """创建用户时的入参模型。"""

    password: str


class UsersReo(UsersBase):
    """用户信息返回模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: str


T = TypeVar("T")


class PageParams(BaseModel):
    """通用分页参数。"""

    page: int = PydanticField(default=1, ge=1, description="页码，从 1 开始")
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


class QueryRequest(PageParams):
    """用户分页列表查询参数。"""

    keyword: Optional[str] = PydanticField(
        default=None,
        description="关键字模糊查询，匹配用户名、姓名、邮箱",
    )
    username: Optional[str] = PydanticField(
        default=None,
        description="按用户名模糊查询",
    )
    full_name: Optional[str] = PydanticField(
        default=None,
        description="按姓名模糊查询",
    )
    email: Optional[str] = PydanticField(
        default=None,
        description="按邮箱模糊查询",
    )
    disabled: Optional[bool] = PydanticField(
        default=False,
        description="按禁用状态精确筛选",
    )

    @field_validator("keyword", "username", "full_name", "email", mode="before")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        """去除首尾空格，并将空字符串视为未传值。"""

        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    def to_repository_filters(self) -> dict[str, str | bool]:
        """将查询参数转换为仓储层可直接消费的过滤条件。"""

        filters: dict[str, str | bool] = {}

        if self.keyword:
            filters["keyword"] = self.keyword
        if self.username:
            filters["username_like"] = self.username
        if self.full_name:
            filters["full_name_like"] = self.full_name
        if self.email:
            filters["email_like"] = self.email
        if self.disabled is not None:
            filters["disabled"] = self.disabled

        return filters


class PageResult(BaseModel, Generic[T]):
    """通用分页返回结构。"""

    data: List[T]
    total: int
    page: int
    pageSize: int
    pages: int
