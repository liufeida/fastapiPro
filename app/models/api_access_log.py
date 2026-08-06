import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field as PydanticField
from sqlalchemy import Column, DateTime, Text
from sqlmodel import Field, SQLModel


class ApiAccessLog(SQLModel, table=True):
    """HTTP API 访问日志表。"""
    __tablename__ = "api_access_log"

    id: Optional[str] = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    trace_id: str = Field(index=True, description="请求级唯一标识")
    method: str = Field(description="HTTP 方法 GET/POST/...")
    path: str = Field(index=True, description="请求路径")
    query_params: Optional[str] = Field(default=None, sa_column=Column(Text), description="query string JSON 字符串")
    request_body: Optional[str] = Field(default=None, sa_column=Column(Text), description="请求 body 原始字符串")
    response_status: int = Field(description="HTTP 响应状态码")
    response_body: Optional[str] = Field(default=None, sa_column=Column(Text), description="响应 body 字符串，流式时为摘要")
    duration_ms: float = Field(description="请求总耗时毫秒")
    is_streaming: bool = Field(default=False, description="是否流式响应")
    is_error: bool = Field(default=False, description="是否异常")
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text), description="异常信息或堆栈")
    ip: Optional[str] = Field(default=None, description="客户端 IP")
    user_agent: Optional[str] = Field(default=None, sa_column=Column(Text), description="User-Agent")
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True)),
        default_factory=lambda: datetime.now(timezone.utc),
    )


class ApiAccessLogReo(SQLModel):
    """响应模型。"""
    model_config = ConfigDict(from_attributes=True)
    id: str | None = None
    trace_id: str
    method: str
    path: str
    query_params: str | None = None
    request_body: str | None = None
    response_status: int
    response_body: str | None = None
    duration_ms: float
    is_streaming: bool = False
    is_error: bool = False
    error_message: str | None = None
    ip: str | None = None
    user_agent: str | None = None
    created_at: datetime | None = None


class ApiAccessLogQueryParams(BaseModel):
    """日志列表查询参数。"""
    page: int = PydanticField(default=1, ge=1)
    pageSize: int = PydanticField(default=20, ge=1, le=100)
    trace_id: Optional[str] = PydanticField(default=None, description="trace_id 精确查询")
    path_keyword: Optional[str] = PydanticField(default=None, description="path 模糊匹配")
    method: Optional[str] = PydanticField(default=None, description="HTTP 方法精确")
    response_status: Optional[int] = PydanticField(default=None, description="状态码精确")
    is_error: Optional[bool] = PydanticField(default=None, description="是否异常")
    start_time: Optional[datetime] = PydanticField(default=None, description="开始时间（含）")
    end_time: Optional[datetime] = PydanticField(default=None, description="结束时间（含）")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.pageSize
