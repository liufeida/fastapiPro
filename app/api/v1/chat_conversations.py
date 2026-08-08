from fastapi import APIRouter

from app.api.dependencies import SessionDeep
from app.core.exceptions import BusinessException, Execute
from app.models.chat_conversation import (
    ChatConversationCreate,
    ChatConversationReo,
    ChatConversationUpdate,
)
from app.models.chat_message import ChatMessageReo
from app.repository.chat_conversation import chat_conversation_repository
from app.repository.chat_message import chat_message_repository
from app.repository.chat_message_attachment import chat_message_attachment_repository
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
    conv = await chat_conversation_service.create_conversation(
        session,
        user_id=data.user_id,
        model_code=data.model_code,
        initial_title=data.title,
    )
    return Execute.response(ChatConversationReo.model_validate(conv))


@router.get(
    "",
    response_model=ResponseModel[dict],
    summary="分页查询会话列表",
    operation_id="listConversations",
)
async def list_conversations(
    session: SessionDeep,
    page: int = 1,
    pageSize: int = 20,
    user_id: str | None = None,
    keyword: str | None = None,
):
    offset = (page - 1) * pageSize
    records = await chat_conversation_repository.list_paginated(
        session, offset, pageSize, user_id=user_id, keyword=keyword
    )
    total = await chat_conversation_repository.count(
        session, user_id=user_id, keyword=keyword
    )
    pages = (total + pageSize - 1) // pageSize if total > 0 else 0
    reos = [ChatConversationReo.model_validate(c) for c in records]
    return Execute.response({
        "records": reos, "total": total, "page": page, "pageSize": pageSize, "pages": pages,
    })


@router.get(
    "/{conv_id}",
    response_model=ResponseModel[dict],
    summary="查询会话详情（含消息列表）",
    operation_id="getConversation",
)
async def get_conversation(
    session: SessionDeep,
    conv_id: str,
):
    conv = await chat_conversation_repository.get_by_id(session, conv_id)
    if not conv or conv.is_deleted:
        raise BusinessException(code=404, message="会话不存在")
    messages = await chat_message_repository.list_by_conversation(session, conv_id)
    msg_ids = [m.id for m in messages]
    att_map = (
        await chat_message_attachment_repository.list_by_message_ids(session, msg_ids)
        if msg_ids
        else {}
    )

    msg_reos = []
    for m in messages:
        reo = ChatMessageReo.model_validate(m)
        reo.attachments = [
            {
                "id": att.id,
                "file_id": att.file_id,
                "url": att.url,
                "filename": att.filename,
                "content_type": att.content_type,
                "type": att.type,
            }
            for att in att_map.get(m.id, [])
        ]
        msg_reos.append(reo)

    conv_reo = ChatConversationReo.model_validate(conv)
    return Execute.response({
        **conv_reo.model_dump(), "messages": msg_reos,
    })


@router.patch(
    "/{conv_id}",
    response_model=ResponseModel[ChatConversationReo],
    summary="重命名会话",
    operation_id="renameConversation",
)
async def rename_conversation(
    session: SessionDeep,
    conv_id: str,
    data: ChatConversationUpdate,
):
    conv = await chat_conversation_repository.get_by_id(session, conv_id)
    if not conv or conv.is_deleted:
        raise BusinessException(code=404, message="会话不存在")
    ok = await chat_conversation_service.rename(session, conv_id, data.title)
    if not ok:
        raise BusinessException(code=400, message="重命名失败")
    conv_updated = await chat_conversation_repository.get_by_id(session, conv_id)
    return Execute.response(ChatConversationReo.model_validate(conv_updated))


@router.delete(
    "/{conv_id}",
    response_model=ResponseModel[dict],
    summary="软删除会话",
    operation_id="deleteConversation",
)
async def delete_conversation(
    session: SessionDeep,
    conv_id: str,
):
    ok = await chat_conversation_service.soft_delete(session, conv_id)
    if not ok:
        raise BusinessException(code=404, message="会话不存在")
    return Execute.response({"deleted": True})
