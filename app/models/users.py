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
    phone: Optional[str]
    disabled: bool = False
    is_deleted: bool = False
    avatar_id: str | None = Field(default=None, foreign_key="file.id")


class Users(UsersBase, table=True):
    """用户表模型。"""

    __tablename__ = "users"
    id: Optional[str] = Field(
        default_factory=lambda: uuid.uuid4().hex, primary_key=True
    )
    hashed_password: str
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True)),
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True)),
        default_factory=lambda: datetime.now(timezone.utc),
    )


class UsersCreate(UsersBase):
    """创建用户时的入参模型。"""

    password: str

    @field_validator("avatar_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        if v == "":
            return None
        return v


class UsersUpdate(SQLModel):
    """更新用户时的入参模型，支持局部更新。"""

    username: str | None = None
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    disabled: bool | None = None
    password: str | None = None
    avatar_id: str | None = None

    @field_validator(
        "username", "full_name", "email", "phone", "password", mode="before"
    )
    @classmethod
    def normalize_update_text(cls, value: str | None) -> str | None:
        """去除首尾空格，并将空字符串视为未传值。"""

        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class UsersReo(UsersBase):
    """用户信息返回模型。"""

    # 允许 Pydantic 从“对象属性”读取数据（而不是只认 dict）
    # 转换对象 UsersReo.model_validate(db_user)，不加的话，只能 UsersReo.model_validate(dict)
    # 不加的话，1.参数有SQLModel的默认有，2.response_model=UsersReo的默认有，3.继承的也有

    # SQLModel ≠ 纯 Pydantic，SQLModel 以及继承的，自带
    model_config = ConfigDict(from_attributes=True)

    id: str | None
    created_at: datetime | None
    updated_at: datetime | None


class UsersLoginReo(UsersReo):
    access_token: str
    refresh_token: str
    token_type: str


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
    phone: Optional[str] = PydanticField(
        default=None,
        description="按手机号模糊查询",
    )
    disabled: Optional[bool] = PydanticField(
        default=False,
        description="按禁用状态精确筛选",
    )

    @field_validator(
        "keyword", "username", "full_name", "email", "phone", mode="before"
    )
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
        if self.phone:
            filters["phone_like"] = self.phone
        if self.disabled is not None:
            filters["disabled"] = self.disabled

        return filters


class PageResult(BaseModel, Generic[T]):
    """通用分页返回结构。"""

    records: List[T]
    total: int
    page: int
    pageSize: int
    pages: int
