import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import ConfigDict
from sqlalchemy import Column, Text, text
from sqlmodel import DateTime, Field, JSON, SQLModel


class ChatMessage(SQLModel, table=True):
    """会话消息表。"""

    __tablename__ = "chat_message"
    __table_args__ = (
        {"extend_existing": True},
    )

    id: Optional[str] = Field(
        default_factory=lambda: uuid.uuid4().hex, primary_key=True
    )
    conversation_id: str = Field(index=True)
    role: str = Field(index=True)
    content: Optional[str] = Field(default=None, sa_column=Column(Text))
    thinking_content: Optional[str] = Field(default=None, sa_column=Column(Text))
    tool_call_id: Optional[str] = Field(
        default=None, index=True,
        description="关联的 tool_call ID（role=tool 时使用）",
    )
    model_code: Optional[str] = Field(
        default=None, index=True,
        description="产生此消息的模型编码（允许同一会话跨模型切换，每条消息独立记录）",
    )
    tool_calls: Optional[dict] = Field(
        default=None, sa_column=Column(JSON),
        description="assistant 消息中的 tool_calls JSON 数组（role=assistant 时使用）",
    )
    tokens_input: Optional[int] = Field(default=None)
    tokens_output: Optional[int] = Field(default=None)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
        default_factory=lambda: datetime.now(timezone.utc),
    )


class ChatMessageReo(SQLModel):
    """消息返回模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    conversation_id: str
    role: str
    content: str | None = None
    thinking_content: str | None = None
    tool_call_id: str | None = None
    model_code: str | None = None
    tool_calls: dict | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None
    created_at: datetime | None = None
    attachments: list[dict] | None = None
