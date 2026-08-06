from typing import Annotated

from fastapi import APIRouter, Body, Path

from app.api.dependencies import SessionDeep
from app.core.exceptions import Execute
from app.models.ai_model_config import PageResult
from app.models.prompt import (
    QueryRequest,
    SystemPromptCreate,
    SystemPromptReo,
    SystemPromptUpdate,
)
from app.schemas.exceptions import ResponseModel
from app.services.prompt import prompt_services

router = APIRouter()


@router.post(
    "",
    response_model=ResponseModel[SystemPromptReo],
    summary="创建系统提示词",
    operation_id="createSystemPrompt",
)
async def create_prompt(session: SessionDeep, data: SystemPromptCreate):
    """创建一条系统提示词。"""
    result = await prompt_services.create(session, data)
    return Execute.response(result)


@router.post(
    "/list",
    response_model=ResponseModel[PageResult[SystemPromptReo]],
    summary="系统提示词分页列表",
    operation_id="getSystemPromptList",
)
async def get_prompt_list(session: SessionDeep, query: Annotated[QueryRequest, Body()]):
    """分页查询系统提示词列表。"""
    result = await prompt_services.list_paginated(session, query)
    return Execute.response(result)


@router.get(
    "/enabled",
    response_model=ResponseModel[list[SystemPromptReo]],
    summary="获取启用的系统提示词列表",
    operation_id="getEnabledPrompts",
)
async def get_enabled_prompts(session: SessionDeep):
    """返回所有启用的系统提示词。"""
    result = await prompt_services.list_enabled(session)
    return Execute.response(result)


@router.get(
    "/{prompt_id}",
    response_model=ResponseModel[SystemPromptReo],
    summary="根据 id 获取系统提示词",
    operation_id="getSystemPromptById",
)
async def get_prompt_by_id(session: SessionDeep, prompt_id: Annotated[str, Path()]):
    """根据 id 获取单条系统提示词。"""
    result = await prompt_services.get_by_id(session, prompt_id)
    return Execute.response(result)


@router.patch(
    "/{prompt_id}",
    response_model=ResponseModel[SystemPromptReo],
    summary="更新系统提示词",
    operation_id="updateSystemPrompt",
)
async def update_prompt(
    session: SessionDeep,
    prompt_id: Annotated[str, Path()],
    data: SystemPromptUpdate,
):
    """局部更新系统提示词。"""
    result = await prompt_services.update(session, prompt_id, data)
    return Execute.response(result)


@router.delete(
    "/{prompt_id}",
    response_model=ResponseModel[SystemPromptReo],
    summary="删除系统提示词",
    operation_id="deleteSystemPrompt",
)
async def delete_prompt(session: SessionDeep, prompt_id: Annotated[str, Path()]):
    """软删除一条系统提示词。"""
    result = await prompt_services.delete(session, prompt_id)
    return Execute.response(result)
