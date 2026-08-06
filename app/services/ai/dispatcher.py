import logging
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.exceptions import BusinessException
from app.models.ai_model_config import AIModelConfig
from app.repository.ai_model_config import ai_model_config_repository
from app.services.ai.base import StreamChunk
from app.services.ai.registry import provider_registry
from app.services.prompt_cache import prompt_cache

logger = logging.getLogger(__name__)


def _build_identity_system(config: AIModelConfig, user_system: Optional[str]) -> str:
    """拼接身份系统提示词。

    始终注入：
      - 身份（model_name + model_code）
      - 当前日期时间（让模型能回答"今天几号"、"星期几"等）
      - 从 prompt_cache 取 DB 配置的系统提示词（按 model_code 精确匹配 → 全局默认）
    用户的 system 追加在最后面（如果有）。
    """
    now = datetime.now(timezone.utc).astimezone()
    identity = (
        f"你是 {config.model_name}（model_code: {config.model_code}）。\n"
        f"当前日期时间: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}（{now.strftime('%A')}）。"
    )
    db_prompt = prompt_cache.resolve(config.model_code)
    db_content = db_prompt.content if db_prompt else ""
    parts = [identity]
    if db_content:
        parts.append(db_content)
    if user_system:
        parts.append(user_system)
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

    async def chat(
        self,
        session: AsyncSession,
        model_code: str,
        prompt: str,
        system: Optional[str] = None,
        thinking: bool = False,
    ) -> str:
        """通用非流式对话。"""
        config = await self.resolve(session, model_code)
        self.check_capability(config, thinking, enable_search=False)
        provider = provider_registry.get(config.provider_code)
        system = _build_identity_system(config, system)
        logger.info(f"AI 调度: model={model_code}, provider={config.provider_code}, thinking={thinking}")

        from app.services.ai_logger import AIChatLogger
        ai_logger = AIChatLogger()
        ai_logger.start(config, prompt, system)

        try:
            result = await provider.chat(config, prompt, system, thinking)
            ai_logger.record_content(result)
            return result
        except Exception as exc:
            ai_logger.record_error(f"{type(exc).__name__}: {str(exc)}")
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
    ) -> AsyncIterator[StreamChunk]:
        """通用流式对话（含工具调用）。

        _config 参数供路由层预校验后传入，避免重复查库。
        """
        config = _config if _config is not None else await self.resolve(session, model_code)
        self.check_capability(config, thinking, enable_search)
        provider = provider_registry.get(config.provider_code)
        system = _build_identity_system(config, system)
        logger.info(
            f"AI 流式调度: model={model_code}, provider={config.provider_code}, "
            f"thinking={thinking}, enable_search={enable_search}"
        )

        from app.services.ai_logger import AIChatLogger, wrap_stream_for_logging
        ai_logger = AIChatLogger()
        ai_logger.start(config, prompt, system)

        try:
            chunk_iter = provider.chat_stream_with_tools(
                config, prompt, system, thinking, enable_search, file_context
            )
            async for chunk in wrap_stream_for_logging(chunk_iter, ai_logger):
                yield chunk
        except Exception as exc:
            ai_logger.record_error(f"{type(exc).__name__}: {str(exc)}")
            ai_logger.enqueue()
            raise


# 单例
ai_dispatcher = AIDispatcher()
