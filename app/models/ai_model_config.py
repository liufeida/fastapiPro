import uuid
from datetime import datetime, timezone
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField
from pydantic import field_validator
from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel


class AIModelConfigBase(SQLModel):
    """AI 模型配置基础字段。"""

    provider_code: str = Field(description="提供商代码，用于路由到对应 Provider 实现（如 deepseek/ollama/openai/anthropic/qwen）")
    model_code: str = Field(description="模型唯一代码，前端传入 model 参数时的匹配依据（如 deepseek-v4-flash）")
    model_name: str = Field(description="模型展示名称（如 DeepSeek V4 Flash）")
    api_key: str | None = Field(default=None, description="API 密钥，响应时脱敏返回")
    base_url: str | None = Field(default=None, description="API 基础地址（如 https://api.deepseek.com、http://localhost:11434）")
    extra_config: dict | None = Field(default=None, sa_column=Column(JSON), description="提供商特有配置，如 Ollama 的 cloud_url/cloud_api_key 等 JSON 键值对")
    supports_thinking: bool = Field(default=False, description="是否支持思考模式（deepseek-reasoner、deepseek-v4-pro 等）")
    supports_tools: bool = Field(default=False, description="是否支持工具调用 / Function Calling")
    supports_stream: bool = Field(default=True, description="是否支持流式输出")
    supports_vision: bool = Field(default=False, description="是否支持视觉输入（图片理解）")
    max_tokens: int | None = Field(default=None, description="单次请求最大生成 tokens，None 由模型默认")
    temperature: float | None = Field(default=None, description="采样温度，0 表示确定性输出，None 由模型默认")
    is_enabled: bool = Field(default=True, description="是否启用，前端拉取可用模型列表与后端路由均会校验")
    is_default: bool = Field(default=False, description="是否为默认模型，同一时刻全局仅一个 True（由 Service 层保证互斥）")
    sort_order: int = Field(default=0, description="排序权重，值越小越靠前（前端模型列表展示用）")
    description: str | None = Field(default=None, description="模型描述，可为空")
    is_deleted: bool = Field(default=False, description="软删除标记，True 时不参与查询与路由")


class AIModelConfig(AIModelConfigBase, table=True):
    """AI 模型配置表模型。"""

    __tablename__ = "ai_model_config"
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


class AIModelConfigCreate(AIModelConfigBase):
    """创建 AI 模型配置时的入参模型。"""


class AIModelConfigUpdate(SQLModel):
    """更新 AI 模型配置时的入参模型，支持局部更新。"""

    provider_code: str | None = None
    model_code: str | None = None
    model_name: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    extra_config: dict | None = None
    supports_thinking: bool | None = None
    supports_tools: bool | None = None
    supports_stream: bool | None = None
    supports_vision: bool | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    is_enabled: bool | None = None
    is_default: bool | None = None
    sort_order: int | None = None
    description: str | None = None

    @field_validator(
        "provider_code",
        "model_code",
        "model_name",
        "api_key",
        "base_url",
        "description",
        mode="before",
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


class AIModelConfigReo(AIModelConfigBase):
    """AI 模型配置返回模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


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
    """AI 模型配置分页列表查询参数。"""

    keyword: Optional[str] = PydanticField(
        default=None,
        description="关键字模糊查询，匹配模型代码、模型名称、描述",
    )
    provider_code: Optional[str] = PydanticField(
        default=None,
        description="按提供商代码精确筛选",
    )
    is_enabled: Optional[bool] = PydanticField(
        default=None,
        description="按启用状态精确筛选",
    )

    @field_validator("keyword", "provider_code", mode="before")
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
        if self.provider_code:
            filters["provider_code"] = self.provider_code
        if self.is_enabled is not None:
            filters["is_enabled"] = self.is_enabled

        return filters


T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    """通用分页返回结构。"""

    records: List[T]
    total: int
    page: int
    pageSize: int
    pages: int
