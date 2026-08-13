from typing import Annotated
from fastapi import APIRouter, Body

from app.api.dependencies import SessionDeep
from app.core.exceptions import Execute
from app.models.common import PageResult
from app.models.chat_conversation import (
    ChatConversationCreate,
    ChatConversationReo,
    ChatConversationUpdate,
    QueryRequest,
)
from app.schemas.exceptions import ResponseModel
from app.services.chat_conversation import chat_conversation_service

router = APIRouter()


@router.post(
    "",
    response_model=ResponseModel[ChatConversationReo],
    summary="创建新会话",
    operation_id="createConversation",
)
async def create_conversation(
    session: SessionDeep,
    data: ChatConversationCreate,
):
    conv = await chat_conversation_service.create_conversation(session, data)
    return Execute.response(conv)


@router.post(
    "/postConversationList",
    response_model=ResponseModel[PageResult[ChatConversationReo]],
    summary="分页查询会话列表",
    operation_id="listConversations",
)
async def post_conversations_list(
    session: SessionDeep,
    query: Annotated[QueryRequest, Body()],
):
    data = await chat_conversation_service.get_conversation_list(session, query)
    return Execute.response(data)


@router.get(
    "/{conv_id}",
    response_model=ResponseModel[dict],
    summary="查询会话详情（含消息列表）",
    operation_id="getConversationById",
)
async def get_conversation_by_id(
    session: SessionDeep,
    conv_id: str,
):
    data = await chat_conversation_service.get_conversation_by_id(session, conv_id)
    return Execute.response(data)


@router.patch(
    "/{conv_id}",
    response_model=ResponseModel[ChatConversationReo],
    summary="重命名会话",
    operation_id="renameConversationById",
)
async def rename_conversation_by_id(
    session: SessionDeep,
    conv_id: str,
    data: ChatConversationUpdate,
):
    data = await chat_conversation_service.rename_conversation_by_id(
        session, conv_id, data
    )
    return Execute.response(data)


@router.delete(
    "/{conv_id}",
    response_model=ResponseModel[ChatConversationReo],
    summary="软删除会话",
    operation_id="deleteConversationById",
)
async def delete_conversation_by_id(
    session: SessionDeep,
    conv_id: str,
):
    data = await chat_conversation_service.soft_delete_by_id(session, conv_id)
    return Execute.response(data)
