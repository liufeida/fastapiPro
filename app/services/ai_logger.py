import json
import time
from typing import AsyncIterator, Optional, TYPE_CHECKING

from app.core.trace import get_trace_id
from app.services.log_queue import LOG_TYPE_AI, log_queue

if TYPE_CHECKING:
    from app.models.ai_model_config import AIModelConfig


class AIChatLogger:
    """AI LLM 调用日志——收集 + 入队。"""

    def __init__(self):
        self._collected: list[str] = []
        self._thinking_parts: list[str] = []
        self._thinking_started = False
        self._thinking_start_time: float | None = None
        self._user_prompt: str = ""
        self._system_prompt: str = ""
        self._messages_str: str = ""
        self._model_code: str = ""
        self._provider_code: str = ""
        self._start_time: float = 0
        self._error: bool = False
        self._error_msg: str | None = None
        self._enqueued: bool = False

    def start(self, config, prompt: str, system: str) -> None:
        """开始记录一次 AI 调用。"""
        self._user_prompt = prompt or ""
        self._system_prompt = system or ""
        self._model_code = config.model_code
        self._provider_code = config.provider_code
        self._start_time = time.perf_counter()
        self._messages_str = json.dumps(
            [{"role": "system", "content": self._system_prompt}, {"role": "user", "content": self._user_prompt}],
            ensure_ascii=False,
        )

    def record_content(self, chunk: str) -> None:
        if chunk:
            self._collected.append(chunk)

    def record_thinking(self, content: str) -> None:
        if content:
            if not self._thinking_started:
                self._thinking_started = True
                self._thinking_start_time = time.perf_counter()
            self._thinking_parts.append(content)

    def record_error(self, msg: str) -> None:
        self._error = True
        self._error_msg = msg

    def enqueue(self) -> None:
        """完成记录并入队（非阻塞、幂等）。"""
        if self._enqueued:
            return
        self._enqueued = True
        elapsed_ms = (time.perf_counter() - self._start_time) * 1000 if self._start_time else 0
        thinking_ms = None
        if self._thinking_start_time is not None and self._thinking_parts:
            thinking_ms = (time.perf_counter() - self._thinking_start_time) * 1000
        log_queue.enqueue(LOG_TYPE_AI, {
            "trace_id": get_trace_id() or "no-trace",
            "model_code": self._model_code,
            "provider_code": self._provider_code,
            "user_prompt": self._user_prompt[:5000],
            "system_prompt": self._system_prompt[:10000],
            "messages": self._messages_str,
            "response_content": "".join(self._collected),
            "thinking_content": "".join(self._thinking_parts) or None,
            "input_tokens": None,
            "output_tokens": None,
            "duration_ms": round(elapsed_ms, 2),
            "thinking_ms": round(thinking_ms, 2) if thinking_ms else None,
            "is_error": self._error,
            "error_message": (self._error_msg or "")[:2000] or None,
        })


ai_chat_logger = AIChatLogger()


async def wrap_stream_for_logging(
    chunk_iter: AsyncIterator,
    logger: AIChatLogger,
) -> AsyncIterator:
    """包装 chat_stream_with_tools 的 AsyncIterator，收集 chunk 并记录日志。"""
    from app.services.ai.base import StreamEvent
    try:
        async for chunk in chunk_iter:
            if isinstance(chunk, str):
                logger.record_content(chunk)
            elif isinstance(chunk, StreamEvent):
                if chunk.type == "thinking":
                    logger.record_thinking(chunk.reasoning or chunk.result or "")
            yield chunk
    except Exception as exc:
        logger.record_error(f"{type(exc).__name__}: {str(exc)}")
        raise
    finally:
        logger.enqueue()
