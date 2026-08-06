import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import ConfigDict
from pydantic import Field as PydanticField
from pydantic import field_validator
from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel

from app.models.ai_model_config import PageParams, PageResult


class SystemPromptBase(SQLModel):
    """系统提示词基础字段。"""

    name: str = Field(description="展示名称")
    prompt_code: str = Field(description="唯一代码，如 deepseek_chat_default")
    content: str = Field(description="提示词正文，可多行")
    model_code: str | None = Field(default=None, description="绑定的 AI 模型；None 表示全局默认")
    is_default: bool = Field(default=False, description="同一 model_code 维度 + 全局维度各一个 True")
    is_enabled: bool = Field(default=True, description="是否启用")
    sort_order: int = Field(default=0, description="排序权重，值越小越靠前")
    description: str | None = Field(default=None, description="描述，可为空")
    is_deleted: bool = Field(default=False, description="软删除标记，True 时不参与查询与路由")


class SystemPrompt(SystemPromptBase, table=True):
    """系统提示词表模型。"""

    __tablename__ = "system_prompt"
    id: Optional[str] = Field(
        default_factory=lambda: uuid.uuid4().hex, primary_key=True
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True)),
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True)),
        default_factory=lambda: datetime.now(timezone.utc),
    )


class SystemPromptCreate(SystemPromptBase):
    """创建系统提示词时的入参模型。"""


class SystemPromptUpdate(SQLModel):
    """更新系统提示词时的入参模型，支持局部更新。"""

    name: str | None = None
    prompt_code: str | None = None
    content: str | None = None
    model_code: str | None = None
    is_default: bool | None = None
    is_enabled: bool | None = None
    sort_order: int | None = None
    description: str | None = None

    @field_validator(
        "name",
        "prompt_code",
        "content",
        "description",
        mode="before",
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


class SystemPromptReo(SystemPromptBase):
    """系统提示词返回模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class QueryRequest(PageParams):
    """系统提示词分页列表查询参数。"""

    keyword: Optional[str] = PydanticField(
        default=None,
        description="关键字模糊查询，匹配 name、prompt_code、content",
    )
    prompt_code: Optional[str] = PydanticField(
        default=None,
        description="按 prompt_code 精确筛选",
    )
    model_code: Optional[str] = PydanticField(
        default=None,
        description="按 model_code 精确筛选",
    )
    is_enabled: Optional[bool] = PydanticField(
        default=None,
        description="按启用状态精确筛选",
    )

    @field_validator("keyword", "prompt_code", "model_code", mode="before")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        """去除首尾空格，并将空字符串视为未传值。"""
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    def to_repository_filters(self) -> dict:
        """将查询参数转换为仓储层可直接消费的过滤条件。"""
        filters: dict = {}

        if self.keyword:
            filters["keyword"] = self.keyword
        if self.prompt_code:
            filters["prompt_code"] = self.prompt_code
        if self.model_code:
            filters["model_code"] = self.model_code
        if self.is_enabled is not None:
            filters["is_enabled"] = self.is_enabled

        return filters
