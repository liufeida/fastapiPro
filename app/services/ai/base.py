import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import AsyncIterator, Optional, Union

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    START = "start"
    THINKING_START = "thinking_start"
    THINKING = "thinking"
    THINKING_END = "thinking_end"
    CONTENT_START = "content_start"
    CONTENT = "content"
    CONTENT_END = "content_end"
    TOOL_START = "tool_start"
    TOOL_RESULT = "tool_result"
    USAGE = "usage"
    END = "end"
    ERROR = "error"
    TOOL = "tool"
    DONE = "Done"


@dataclass
class StreamEvent:
    """统一流式事件模型——覆盖所有 SSE 事件类型。

    type字段值见 EventType 枚举，各事件使用的字段：
      start:          request_id, model, model_name, thinking, enable_search, timestamp
      thinking_start: timestamp
      thinking:       reasoning (增量文本)
      thinking_end:   reasoning (完整文本), total_chars
      content_start:  timestamp
      content:        content (增量文本)
      content_end:    content (完整文本), total_chars
      tool_start:     tool_call_id, name, args
      tool_result:    tool_call_id, name, result, elapsed_ms
      usage:          prompt_tokens, completion_tokens, total_tokens, reasoning_tokens
      end:            request_id, stop_reason, elapsed_ms
      error:          message, code
    """

    type: str
    request_id: Optional[str] = None
    timestamp: Optional[str] = None
    model: Optional[str] = None
    model_name: Optional[str] = None
    thinking: Optional[bool] = None
    enable_search: Optional[bool] = None
    reasoning: Optional[str] = None
    content: Optional[str] = None
    total_chars: Optional[int] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    args: Optional[dict] = None
    result: Optional[str] = None
    elapsed_ms: Optional[int] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    stop_reason: Optional[str] = None
    message: Optional[str] = None
    code: Optional[int] = None


@dataclass
class ToolEvent(StreamEvent):
    """旧版工具事件——保留为向后兼容。type只支持thinking/tool/tool_result。"""

    def __init__(self, type: str, name: str, args: Optional[dict] = None, result: Optional[str] = None):
        if type not in ("thinking", "tool", "tool_result"):
            raise ValueError(f"ToolEvent 不支持 type={type}，请使用 StreamEvent")
        super().__init__(type=type, name=name, args=args, result=result)


StreamChunk = Union[str, StreamEvent]


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
