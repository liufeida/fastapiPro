import logging
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.exceptions import BusinessException
from app.models.ai_model_config import AIModelConfig
from app.models.prompt import SystemPrompt
from app.repository.ai_model_config import ai_model_config_repository
from app.services.ai.base import StreamChunk
from app.services.ai.registry import provider_registry
from app.services.prompt_cache import prompt_cache

logger = logging.getLogger(__name__)


def _format_exception(exc: Exception) -> str:
    """统一格式化异常信息，确保 BusinessException 的 code/message 都能展示。"""
    from app.core.exceptions import BusinessException
    if isinstance(exc, BusinessException):
        return f"{type(exc).__name__}(code={exc.code}): {exc.message}"
    return f"{type(exc).__name__}: {exc}"


def _append_unique(parts: list[str], content: str | None) -> None:
    if content and content not in parts:
        parts.append(content)


def _build_identity_system(
    config: AIModelConfig,
    user_system: Optional[str],
    extra_prompt: Optional[SystemPrompt] = None,
) -> str:
    now = datetime.now(timezone.utc).astimezone()
    identity = (
        f"你是 {config.model_name}（model_code: {config.model_code}）。\n"
        f"当前日期时间: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}（{now.strftime('%A')}）。"
    )
    parts: list[str] = [identity]

    global_default = prompt_cache.global_default
    if global_default and global_default.content:
        _append_unique(parts, global_default.content)

    db_prompt = prompt_cache.resolve(config.model_code)
    if db_prompt and db_prompt.content:
        _append_unique(parts, db_prompt.content)

    if extra_prompt and extra_prompt.content:
        _append_unique(parts, extra_prompt.content)

    if user_system:
        _append_unique(parts, user_system)

    return "\n".join(parts)


class AIDispatcher:
    """AI 调度器：根据 model_code 查库 → 取 provider → 调用，并做能力校验。"""

    async def resolve(self, session: AsyncSession, model_code: str) -> AIModelConfig:
        """根据 model_code 查询配置，校验启用状态。

        - 记录不存在或已软删除：抛 404
        - is_enabled=False：抛 404
        """
        config = await ai_model_config_repository.get_by_model_code(session, model_code)
        if not config or not config.is_enabled:
            raise BusinessException(code=404, message="模型不可用或未配置")
        return config

    def check_capability(self, config: AIModelConfig, thinking: bool, enable_search: bool) -> None:
        """校验模型能力是否匹配请求参数。

        - thinking=True 但 supports_thinking=False：抛 400
        - enable_search=True 但 supports_tools=False：抛 400
        """
        if thinking and not config.supports_thinking:
            raise BusinessException(code=400, message="该模型不支持思考模式")
        if enable_search and not config.supports_tools:
            raise BusinessException(code=400, message="该模型不支持工具调用")

    async def _load_optional_prompt(
        self, session: AsyncSession, prompt_code: str
    ) -> SystemPrompt | None:
        cached = prompt_cache.get_optional_by_code(prompt_code)
        if cached is not None:
            return cached

        from app.repository.prompt import prompt_repository
        db_prompt = await prompt_repository.get_by_prompt_code(session, prompt_code)
        if db_prompt is None:
            raise BusinessException(code=404, message=f"提示词不存在: {prompt_code}")
        if not db_prompt.is_enabled:
            raise BusinessException(code=400, message="该提示词已禁用，不可选择")
        if db_prompt.model_code is not None:
            raise BusinessException(code=400, message="该提示词已被模型绑定，不可选择")
        if db_prompt.is_default:
            raise BusinessException(code=400, message="该提示词是全局默认，不可选择")
        return db_prompt

    async def chat(
        self,
        session: AsyncSession,
        model_code: str,
        prompt: str,
        system: Optional[str] = None,
        thinking: bool = False,
        prompt_code: str | None = None,
    ) -> str:
        """通用非流式对话。"""
        from app.services.ai_logger import AIChatLogger
        ai_logger = AIChatLogger()
        ai_logger.start(model_code, prompt, system)

        try:
            config = await self.resolve(session, model_code)
            self.check_capability(config, thinking, enable_search=False)
            ai_logger.bind_config(config)
            provider = provider_registry.get(config.provider_code)
            extra_prompt = None
            if prompt_code:
                extra_prompt = await self._load_optional_prompt(session, prompt_code)
            system_prompt = _build_identity_system(config, system, extra_prompt)
            ai_logger._system_prompt = system_prompt
            logger.info(f"AI 调度: model={model_code}, provider={config.provider_code}, thinking={thinking}")

            result = await provider.chat(config, prompt, system_prompt, thinking)
            ai_logger.record_content(result)
            return result
        except Exception as exc:
            ai_logger.record_error(_format_exception(exc))
            raise
        finally:
            ai_logger.enqueue()

    async def chat_stream_with_tools(
        self,
        session: AsyncSession,
        model_code: str,
        prompt: str,
        system: Optional[str] = None,
        thinking: bool = False,
        enable_search: bool = False,
        file_context: Optional[str] = None,
        _config: Optional[AIModelConfig] = None,
        prompt_code: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """通用流式对话（含工具调用）。

        _config 参数供路由层预校验后传入，避免重复查库。
        """
        from app.services.ai_logger import AIChatLogger, wrap_stream_for_logging
        ai_logger = AIChatLogger()
        ai_logger.start(model_code, prompt, system)

        config = _config
        try:
            if config is None:
                config = await self.resolve(session, model_code)
            self.check_capability(config, thinking, enable_search)
            ai_logger.bind_config(config)
            provider = provider_registry.get(config.provider_code)
            extra_prompt = None
            if prompt_code:
                extra_prompt = await self._load_optional_prompt(session, prompt_code)
            system_prompt = _build_identity_system(config, system, extra_prompt)
            ai_logger._system_prompt = system_prompt
            logger.info(
                f"AI 流式调度: model={model_code}, provider={config.provider_code}, "
                f"thinking={thinking}, enable_search={enable_search}"
            )

            chunk_iter = provider.chat_stream_with_tools(
                config, prompt, system_prompt, thinking, enable_search, file_context
            )
            async for chunk in wrap_stream_for_logging(chunk_iter, ai_logger):
                yield chunk
        except Exception as exc:
            ai_logger.record_error(_format_exception(exc))
            ai_logger.enqueue()
            raise


# 单例
ai_dispatcher = AIDispatcher()
