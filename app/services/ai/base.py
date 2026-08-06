import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class ToolEvent:
    """工具调用相关事件，供路由层区分 SSE 事件类型。

    type="tool": 模型决定调用工具，args 为工具入参
    type="tool_result": 后端执行工具完毕，result 为执行结果
    type="thinking": 模型的思考过程内容（reasoning_content）
    """

    type: str  # "tool" | "tool_result" | "thinking"
    name: str
    args: Optional[dict] = None
    result: Optional[str] = None


# 流式生成器产出类型：内容块(str) 或 工具事件(ToolEvent)
StreamChunk = Union[str, ToolEvent]


class AIProvider(ABC):
    """AI 模型提供商抽象基类。

    所有大模型接入必须实现该基类，并注册到 ProviderRegistry。
    禁止在路由层直接裸调第三方 HTTP。

    config 参数类型使用 TYPE_CHECKING 延迟导入，避免循环依赖。
    config 为 app.models.ai_model_config.AIModelConfig 实例，包含
    provider_code、api_key、base_url、model_name 等运行时配置。
    """

    @abstractmethod
    async def chat(self, config, prompt: str, system: Optional[str] = None, thinking: bool = False) -> str:
        """非流式对话，返回完整回复。"""
        ...

    @abstractmethod
    async def chat_stream(self, config, prompt: str, system: Optional[str] = None, thinking: bool = False) -> AsyncIterator[StreamChunk]:
        """流式对话，逐块返回内容。开启 thinking 时会先输出思考内容。"""
        ...

    @abstractmethod
    async def chat_stream_with_tools(self, config, prompt: str, system: Optional[str] = None, thinking: bool = False, enable_search: bool = False, file_context: Optional[str] = None) -> AsyncIterator[StreamChunk]:
        """增强版流式对话：支持文件上下文与联网搜索工具调用循环。"""
        ...
