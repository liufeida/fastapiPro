import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, text
from sqlmodel import Field, SQLModel


class ChatMessageAttachment(SQLModel, table=True):
    """消息附件表。"""

    __tablename__ = "chat_message_attachment"

    id: Optional[str] = Field(
        default_factory=lambda: uuid.uuid4().hex, primary_key=True
    )
    message_id: str = Field(index=True)
    file_id: Optional[str] = Field(default=None)
    url: str
    filename: str
    content_type: Optional[str] = Field(default=None)
    type: str = Field(default="image", index=True)
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=text("NOW()")),
        default_factory=lambda: datetime.now(timezone.utc),
    )
