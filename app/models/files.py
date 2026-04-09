import uuid
from datetime import datetime, timezone

from pydantic import ConfigDict
from sqlmodel import Column, DateTime, Field, SQLModel


class FileBase(SQLModel):
    """文件元数据基类."""

    filename: str
    file_path: str
    file_size: int
    content_type: str


class File(FileBase, table=True):
    """用于存储上传文件元数据的数据库表."""

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
