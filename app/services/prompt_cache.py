from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.prompt import SystemPrompt
from app.repository.prompt import prompt_repository


class PromptCache:
    """系统提示词内存缓存。"""

    def __init__(self):
        self._cache: dict[str, SystemPrompt] = {}
        self._global_default_prompt: SystemPrompt | None = None
        self._model_defaults: dict[str, SystemPrompt] = {}
        self._optional_prompts: dict[str, SystemPrompt] = {}

    async def warm_up(self, session: AsyncSession) -> None:
        """从 DB 加载所有未删除且启用的 Prompt。

        - model_code 为 None 且 is_default=True → 全局默认提示词
        - model_code 不为 None 且 is_default=True → 各模型默认提示词
        - model_code 为 None、is_default=False、is_enabled=True → 可选提示词
        """
        self._cache.clear()
        self._global_default_prompt = None
        self._model_defaults.clear()
        self._optional_prompts.clear()

        prompts = await prompt_repository.list_enabled(session)
        for p in prompts:
            if p.model_code is None and p.is_default:
                self._global_default_prompt = p
            elif p.model_code is not None and p.is_default:
                self._model_defaults[p.model_code] = p
            elif p.model_code is None and not p.is_default and p.is_enabled:
                self._optional_prompts[p.prompt_code] = p

    async def refresh(self, session: AsyncSession) -> None:
        """清空后重新 warm_up。"""
        await self.warm_up(session)

    @property
    def global_default(self) -> SystemPrompt | None:
        """返回全局默认提示词（model_code 为 None 且 is_default=True）。"""
        return self._global_default_prompt

    def get_optional_by_code(self, prompt_code: str) -> SystemPrompt | None:
        """根据 prompt_code 获取可选提示词，不存在则返回 None。"""
        return self._optional_prompts.get(prompt_code)

    def resolve(self, model_code: str | None) -> SystemPrompt | None:
        """返回 model_code 对应的默认提示词，无则返回 None。

        全局默认提示词通过 global_default 属性单独获取。
        """
        if model_code and model_code in self._model_defaults:
            return self._model_defaults[model_code]
        return None


prompt_cache = PromptCache()
