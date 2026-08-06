"""AI 模型统一接入平台：Provider 抽象、注册表、调度器。"""

# 导入 provider 模块，触发注册副作用（register 调用）
from app.services.ai import deepseek_provider  # noqa: F401
from app.services.ai import ollama_provider  # noqa: F401
from app.services.ai import qwen_provider  # noqa: F401

# 导出常用符号，方便外部 from app.services.ai import xxx
from app.services.ai.base import AIProvider, StreamChunk, ToolEvent
from app.services.ai.dispatcher import ai_dispatcher
from app.services.ai.registry import provider_registry
from app.services.ai.sse import build_sse

__all__ = [
    "AIProvider",
    "StreamChunk",
    "ToolEvent",
    "ai_dispatcher",
    "provider_registry",
    "build_sse",
]
