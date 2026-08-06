import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field as PydanticField
from sqlalchemy import Column, DateTime, Text
from sqlmodel import Field, SQLModel


class AIChatLog(SQLModel, table=True):
    """AI LLM 调用日志表。"""
    __tablename__ = "ai_chat_log"

    id: Optional[str] = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    trace_id: str = Field(index=True, description="关联 api_access_log")
    model_code: str = Field(description="模型代码", index=True)
    provider_code: str = Field(description="提供商代码")
    user_prompt: Optional[str] = Field(default=None, sa_column=Column(Text), description="前端传入的原始 prompt")
    system_prompt: Optional[str] = Field(default=None, sa_column=Column(Text), description="实际发给 LLM 的完整 system")
    messages: Optional[str] = Field(default=None, sa_column=Column(Text), description="完整 messages 数组 JSON 字符串")
    response_content: Optional[str] = Field(default=None, sa_column=Column(Text), description="LLM 返回的完整内容")
    thinking_content: Optional[str] = Field(default=None, sa_column=Column(Text), description="thinking 模式推理链")
    input_tokens: Optional[int] = Field(default=None)
    output_tokens: Optional[int] = Field(default=None)
    duration_ms: float = Field(description="AI 调用总耗时")
    thinking_ms: Optional[float] = Field(default=None, description="thinking 阶段耗时")
    is_error: bool = Field(default=False)
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True)),
        default_factory=lambda: datetime.now(timezone.utc),
    )


class AIChatLogReo(SQLModel):
    model_config = ConfigDict(from_attributes=True)
    id: str | None = None
    trace_id: str
    model_code: str
    provider_code: str
    user_prompt: str | None = None
    system_prompt: str | None = None
    messages: str | None = None
    response_content: str | None = None
    thinking_content: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: float
    thinking_ms: float | None = None
    is_error: bool = False
    error_message: str | None = None
    created_at: datetime | None = None


class AIChatLogQueryParams(BaseModel):
    page: int = PydanticField(default=1, ge=1)
    pageSize: int = PydanticField(default=20, ge=1, le=100)
    trace_id: Optional[str] = PydanticField(default=None)
    model_code: Optional[str] = PydanticField(default=None)
    provider_code: Optional[str] = PydanticField(default=None)
    is_error: Optional[bool] = PydanticField(default=None)
    start_time: Optional[datetime] = PydanticField(default=None)
    end_time: Optional[datetime] = PydanticField(default=None)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.pageSize
