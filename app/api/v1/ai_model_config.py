from typing import Annotated

from fastapi import APIRouter, Body, Path

from app.api.dependencies import SessionDeep
from app.core.exceptions import Execute
from app.models.ai_model_config import (
    AIModelConfigCreate,
    AIModelConfigReo,
    AIModelConfigUpdate,
    PageResult,
    QueryRequest,
)
from app.schemas.exceptions import ResponseModel
from app.services.ai_model_config import ai_model_config_services

router = APIRouter()


@router.post(
    "",
    response_model=ResponseModel[AIModelConfigReo],
    summary="创建 AI 模型配置",
    operation_id="createAIModelConfig",
)
async def create_config(session: SessionDeep, data: AIModelConfigCreate):
    """创建一条 AI 模型配置，含唯一性校验与默认模型互斥。"""
    result = await ai_model_config_services.create(session, data)
    return Execute.response(result)


@router.post(
    "/list",
    response_model=ResponseModel[PageResult[AIModelConfigReo]],
    summary="AI 模型配置分页列表",
    operation_id="getAIModelConfigList",
)
async def get_config_list(session: SessionDeep, query: Annotated[QueryRequest, Body()]):
    """分页查询 AI 模型配置列表，支持 keyword/provider_code/is_enabled 过滤。"""
    result = await ai_model_config_services.list_paginated(session, query)
    return Execute.response(result)


@router.get(
    "/enabled",
    response_model=ResponseModel[list[AIModelConfigReo]],
    summary="获取启用的 AI 模型列表（前端用）",
    operation_id="getEnabledAIModels",
)
async def get_enabled_configs(session: SessionDeep):
    """返回所有启用的模型配置，按 sort_order 升序排列，响应不含 api_key。"""
    result = await ai_model_config_services.list_enabled(session)
    return Execute.response(result)


@router.get(
    "/{config_id}",
    response_model=ResponseModel[AIModelConfigReo],
    summary="根据 id 获取 AI 模型配置",
    operation_id="getAIModelConfigById",
)
async def get_config_by_id(session: SessionDeep, config_id: Annotated[str, Path()]):
    """根据 id 获取单条配置（api_key 脱敏）。"""
    result = await ai_model_config_services.get_by_id(session, config_id)
    return Execute.response(result)


@router.patch(
    "/{config_id}",
    response_model=ResponseModel[AIModelConfigReo],
    summary="更新 AI 模型配置",
    operation_id="updateAIModelConfig",
)
async def update_config(
    session: SessionDeep,
    config_id: Annotated[str, Path(description="配置 ID")],
    data: AIModelConfigUpdate,
):
    """局部更新配置，支持唯一性校验与默认模型互斥。"""
    result = await ai_model_config_services.update(session, config_id, data)
    return Execute.response(result)


@router.delete(
    "/{config_id}",
    response_model=ResponseModel[AIModelConfigReo],
    summary="删除 AI 模型配置",
    operation_id="deleteAIModelConfig",
)
async def delete_config(session: SessionDeep, config_id: Annotated[str, Path()]):
    """软删除一条配置。"""
    result = await ai_model_config_services.delete(session, config_id)
    return Execute.response(result)
