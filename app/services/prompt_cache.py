from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.prompt import SystemPrompt
from app.repository.prompt import prompt_repository


class PromptCache:
    """系统提示词内存缓存。"""

    def __init__(self):
        self._cache: dict[str, SystemPrompt] = {}
        self._global_default: SystemPrompt | None = None

    async def warm_up(self, session: AsyncSession) -> None:
        """从 DB 加载所有未删除且启用的 Prompt，填充 _cache 和 _global_default。"""
        self._cache.clear()
        self._global_default = None

        prompts = await prompt_repository.list_enabled(session)
        for p in prompts:
            if p.is_default:
                if p.model_code is None:
                    self._global_default = p
                else:
                    self._cache[p.model_code] = p

    async def refresh(self, session: AsyncSession) -> None:
        """清空后重新 warm_up。"""
        await self.warm_up(session)

    def resolve(self, model_code: str | None) -> SystemPrompt | None:
        """优先精确匹配 _cache[model_code]，否则返回 _global_default。"""
        if model_code and model_code in self._cache:
            return self._cache[model_code]
        return self._global_default


prompt_cache = PromptCache()
