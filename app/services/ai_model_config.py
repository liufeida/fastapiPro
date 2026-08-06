from fastapi import HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.exceptions import BusinessException
from app.models.ai_model_config import (
    AIModelConfig,
    AIModelConfigCreate,
    AIModelConfigReo,
    AIModelConfigUpdate,
    PageResult,
    QueryRequest,
)
from app.repository.ai_model_config import ai_model_config_repository


class AIModelConfigServices:
    """AI 模型配置服务层。"""

    MASK_TOKEN = "****"

    @staticmethod
    def mask_api_key(key: str | None) -> str | None:
        """脱敏 API Key。

        规则：长度 <= 8 时全替换为 ****；否则保留前 3 位 + 后 4 位，中间用 **** 替代。
        None 透传。
        """
        if not key:
            return None
        if len(key) <= 8:
            return "****"
        return f"{key[:3]}****{key[-4:]}"

    @staticmethod
    def _looks_masked(key: str | None) -> bool:
        """判断 api_key 是否看起来是脱敏格式（含 ****）。"""
        return bool(key and "****" in key)

    def _to_reo(self, config: AIModelConfig) -> AIModelConfigReo:
        """将数据库模型转为响应模型，并对 api_key 脱敏。"""
        config_dict = config.model_dump()
        config_dict["api_key"] = self.mask_api_key(config_dict.get("api_key"))
        return AIModelConfigReo.model_validate(config_dict)

    async def create(self, session: AsyncSession, data: AIModelConfigCreate) -> AIModelConfigReo:
        """创建模型配置。

        - 唯一性校验：(provider_code, model_code) 不可重复
        - 若 is_default=True，先创建拿到 id，再清理其他默认标记（exclude_id=自身 id）
        """
        # 唯一性校验
        exists = await ai_model_config_repository.exists_by_provider_and_code(
            session, data.provider_code, data.model_code
        )
        if exists:
            raise BusinessException(code=400, message="该模型代码已存在")

        # 防护：拒绝写入脱敏格式的 api_key（前端可能把 GET 响应里的脱敏 key 原样 POST 回来）
        if self._looks_masked(data.api_key):
            raise BusinessException(
                code=400,
                message="api_key 不能是脱敏格式（含 ****），请填入完整值或留空",
            )

        config_dict = data.model_dump()
        db_config = await ai_model_config_repository.create(session, config_dict)

        # 若 is_default=True，清理其他默认（exclude_id=自身 id，不会清理刚创建的自身）
        if db_config.is_default:
            await ai_model_config_repository.clear_other_defaults(session, exclude_id=db_config.id)

        return self._to_reo(db_config)

    async def get_by_id(self, session: AsyncSession, config_id: str) -> AIModelConfigReo:
        """根据 id 获取配置（脱敏）。"""
        db_config = await ai_model_config_repository.get_by_id(session, config_id)
        if not db_config:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI model config not found")
        return self._to_reo(db_config)

    async def list_paginated(self, session: AsyncSession, query: QueryRequest) -> PageResult[AIModelConfigReo]:
        """分页查询配置列表。"""
        filters = query.to_repository_filters()
        configs = await ai_model_config_repository.list_paginated(
            session, offset=query.offset, limit=query.limit, **filters
        )
        total = await ai_model_config_repository.count(session, **filters)
        pages = (total + query.pageSize - 1) // query.pageSize if total > 0 else 0
        records = [self._to_reo(c) for c in configs]
        return PageResult(
            records=records,
            total=total,
            page=query.page,
            pageSize=query.pageSize,
            pages=pages,
        )

    async def list_enabled(self, session: AsyncSession) -> list[AIModelConfigReo]:
        """获取启用的模型列表（前端用，响应中 exclude api_key）。

        注意：此方法返回的 Reo 中 api_key 应为 None（不返回给前端）。
        """
        configs = await ai_model_config_repository.list_enabled(session)
        records = []
        for c in configs:
            reo = self._to_reo(c)
            reo.api_key = None  # 前端列表不返回 api_key
            records.append(reo)
        return records

    async def update(self, session: AsyncSession, config_id: str, data: AIModelConfigUpdate) -> AIModelConfigReo:
        """更新配置（局部更新）。

        - exclude_unset 模式
        - 若改了 provider_code 或 model_code，重新做唯一性校验
        - 若改 is_default=True，清理其他默认
        """
        db_config = await ai_model_config_repository.get_by_id(session, config_id)
        if not db_config:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI model config not found")

        update_data = data.model_dump(exclude_unset=True, exclude_none=True)
        if not update_data:
            return self._to_reo(db_config)

        # 防护：如果 update_data 里 api_key 是脱敏格式，跳过该字段（不覆盖原值）
        if self._looks_masked(update_data.get("api_key")):
            del update_data["api_key"]

        # 唯一性校验（若改了 provider_code 或 model_code）
        new_provider = update_data.get("provider_code", db_config.provider_code)
        new_code = update_data.get("model_code", db_config.model_code)
        if "provider_code" in update_data or "model_code" in update_data:
            exists = await ai_model_config_repository.exists_by_provider_and_code(
                session, new_provider, new_code, exclude_id=config_id
            )
            if exists:
                raise BusinessException(code=400, message="该模型代码已存在")

        # 默认互斥
        if update_data.get("is_default"):
            await ai_model_config_repository.clear_other_defaults(session, exclude_id=config_id)

        updated = await ai_model_config_repository.update(session, config_id, update_data)
        return self._to_reo(updated)

    async def delete(self, session: AsyncSession, config_id: str) -> AIModelConfigReo:
        """软删除配置。

        若删除的是默认模型，正常软删除（不自动转移默认标记，由前端重新指定）。
        """
        db_config = await ai_model_config_repository.get_by_id(session, config_id)
        if not db_config:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI model config not found")

        deleted = await ai_model_config_repository.soft_delete(session, config_id)
        return self._to_reo(deleted)


ai_model_config_services = AIModelConfigServices()
