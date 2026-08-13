import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic import Field as PydanticField
from sqlalchemy import Column, DateTime, text
from sqlmodel import Field, SQLModel

from app.models.common import PageParams


class ChatConversation(SQLModel, table=True):
    """会话表。"""

    __tablename__ = "chat_conversation"

    id: Optional[str] = Field(
        default_factory=lambda: uuid.uuid4().hex, primary_key=True
    )
    user_id: Optional[str] = Field(default=None, index=True)
    title: Optional[str] = Field(default=None)
    model_code: Optional[str] = Field(default=None, index=True)
    is_deleted: bool = Field(default=False)
    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("NOW()"),
        ),
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True),
            server_default=text("NOW()"),
            onupdate=text("NOW()"),
        ),
        default_factory=lambda: datetime.now(timezone.utc),
    )


class ChatConversationReo(SQLModel):
    """会话返回模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    user_id: str | None = None
    title: str | None = None
    model_code: str | None = None
    is_deleted: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ChatConversationCreate(SQLModel):
    """创建会话入参。"""

    title: Optional[str] = None
    model_code: Optional[str] = None
    user_id: Optional[str] = None


class ChatConversationUpdate(SQLModel):
    """更新会话入参。"""

    title: Optional[str] = None


class QueryRequest(PageParams):
    """会话分页列表查询参数。"""

    keyword: Optional[str] = PydanticField(
        default=None,
        description="关键字模糊查询，匹配标题",
    )
    user_id: Optional[str] = None

    @field_validator("keyword", "user_id", mode="before")
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
        if self.user_id:
            filters["user_id"] = self.user_id

        return filters
