from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.exceptions import BusinessException
from app.models.ai_model_config import PageResult
from app.models.prompt import (
    SystemPrompt,
    SystemPromptCreate,
    SystemPromptReo,
    SystemPromptUpdate,
    QueryRequest,
)
from app.repository.prompt import prompt_repository
from app.services.prompt_cache import prompt_cache


class PromptServices:
    """系统提示词服务层。"""

    def _to_reo(self, prompt: SystemPrompt) -> SystemPromptReo:
        """将数据库模型转为响应模型。"""
        return SystemPromptReo.model_validate(prompt.model_dump())

    async def create(
        self, session: AsyncSession, data: SystemPromptCreate
    ) -> SystemPromptReo:
        """创建系统提示词。

        - prompt_code 唯一性校验
        - 如果 model_code 有值且 is_default=True，先创建拿到 id，再 clear_other_model_defaults
        - 如果 model_code 为 None 且 is_default=True，先创建拿到 id，再 clear_global_default
        - 创建完成后调用 prompt_cache.refresh()
        """
        exists = await prompt_repository.exists_by_prompt_code(session, data.prompt_code)
        if exists:
            raise BusinessException(code=400, message="该提示词代码已存在")

        if data.model_code:
            bound = await prompt_repository.is_model_code_bound(session, data.model_code)
            if bound:
                raise BusinessException(code=400, message="该模型已被其他提示词绑定")

        prompt_dict = data.model_dump()
        db_prompt = await prompt_repository.create(session, prompt_dict)

        if db_prompt.is_default:
            if db_prompt.model_code:
                await prompt_repository.clear_other_model_defaults(
                    session, model_code=db_prompt.model_code, exclude_id=db_prompt.id
                )
            else:
                await prompt_repository.clear_global_default(
                    session, exclude_id=db_prompt.id
                )

        await prompt_cache.refresh(session)
        return self._to_reo(db_prompt)

    async def get_by_id(
        self, session: AsyncSession, prompt_id: str
    ) -> SystemPromptReo:
        """根据 id 获取提示词。"""
        db_prompt = await prompt_repository.get_by_id(session, prompt_id)
        if not db_prompt:
            raise BusinessException(code=404, message="System prompt not found")
        return self._to_reo(db_prompt)

    async def list_paginated(
        self, session: AsyncSession, query: QueryRequest
    ) -> PageResult[SystemPromptReo]:
        """分页查询提示词列表。"""
        filters = query.to_repository_filters()
        prompts = await prompt_repository.list_paginated(
            session, offset=query.offset, limit=query.limit, **filters
        )
        total = await prompt_repository.count(session, **filters)
        pages = (total + query.pageSize - 1) // query.pageSize if total > 0 else 0
        records = [self._to_reo(p) for p in prompts]
        return PageResult(
            records=records,
            total=total,
            page=query.page,
            pageSize=query.pageSize,
            pages=pages,
        )

    async def list_enabled(self, session: AsyncSession) -> list[SystemPromptReo]:
        """获取所有启用的提示词。"""
        prompts = await prompt_repository.list_enabled(session)
        return [self._to_reo(p) for p in prompts]

    async def update(
        self, session: AsyncSession, prompt_id: str, data: SystemPromptUpdate
    ) -> SystemPromptReo:
        """更新提示词（局部更新）。

        - 同样的唯一性校验（if prompt_code changed）
        - 默认互斥逻辑同 create
        - prompt_cache.refresh()
        """
        db_prompt = await prompt_repository.get_by_id(session, prompt_id)
        if not db_prompt:
            raise BusinessException(code=404, message="System prompt not found")

        update_data = data.model_dump(exclude_unset=True, exclude_none=True)
        if not update_data:
            return self._to_reo(db_prompt)

        if "prompt_code" in update_data:
            exists = await prompt_repository.exists_by_prompt_code(
                session, update_data["prompt_code"], exclude_id=prompt_id
            )
            if exists:
                raise BusinessException(code=400, message="该提示词代码已存在")

        new_model_code = update_data.get("model_code")
        if new_model_code:
            bound = await prompt_repository.is_model_code_bound(
                session, new_model_code, exclude_id=prompt_id
            )
            if bound:
                raise BusinessException(code=400, message="该模型已被其他提示词绑定")

        new_is_default = update_data.get("is_default")
        if new_is_default:
            new_model_code = update_data.get("model_code", db_prompt.model_code)
            if new_model_code:
                await prompt_repository.clear_other_model_defaults(
                    session, model_code=new_model_code, exclude_id=prompt_id
                )
            else:
                await prompt_repository.clear_global_default(
                    session, exclude_id=prompt_id
                )

        updated = await prompt_repository.update(session, prompt_id, update_data)
        await prompt_cache.refresh(session)
        return self._to_reo(updated)

    async def delete(self, session: AsyncSession, prompt_id: str) -> SystemPromptReo:
        """软删除提示词 + prompt_cache.refresh()。"""
        db_prompt = await prompt_repository.get_by_id(session, prompt_id)
        if not db_prompt:
            raise BusinessException(code=404, message="System prompt not found")

        deleted = await prompt_repository.soft_delete(session, prompt_id)
        await prompt_cache.refresh(session)
        return self._to_reo(deleted)


prompt_services = PromptServices()
