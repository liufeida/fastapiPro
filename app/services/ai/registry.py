import logging
from typing import Dict

from app.core.exceptions import BusinessException
from app.services.ai.base import AIProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """AI Provider 注册表，按 provider_code 注册与获取 Provider 实例。"""

    def __init__(self):
        self._providers: Dict[str, AIProvider] = {}

    def register(self, provider_code: str, provider: AIProvider) -> None:
        """注册一个 Provider 实例。重复注册会覆盖并记录警告。"""
        if provider_code in self._providers:
            logger.warning(f"Provider '{provider_code}' 已注册，将被覆盖")
        self._providers[provider_code] = provider
        logger.info(f"已注册 AI Provider: {provider_code}")

    def get(self, provider_code: str) -> AIProvider:
        """获取已注册的 Provider。未注册时抛 BusinessException。"""
        provider = self._providers.get(provider_code)
        if provider is None:
            raise BusinessException(
                code=500,
                message=f"未注册的模型提供商: {provider_code}",
            )
        return provider

    def list_providers(self) -> list[str]:
        """列出所有已注册的 provider_code。"""
        return list(self._providers.keys())


# 单例
provider_registry = ProviderRegistry()
