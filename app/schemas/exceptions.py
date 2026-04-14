# 用于令牌端点响应的 Pydantic 模型
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ResponseModel(BaseModel, Generic[T]):
    code: int = 200
    message: str = ""
    data: Optional[T] = None
    success: bool = True


class ErrorResponseModel(ResponseModel):
    success: bool = False
    detail: Optional[Any] = None  # 额外细节（如字段校验失败列表）
