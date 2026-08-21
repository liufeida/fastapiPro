from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.exceptions import BusinessException
from app.models.chat_message import ChatMessageReo
from app.models.common import PageResult
from app.models.chat_conversation import (
    ChatConversation,
    ChatConversationCreate,
    ChatConversationReo,
    ChatConversationUpdate,
    QueryRequest,
)
from app.repository.chat_conversation import chat_conversation_repository
from app.repository.chat_message import chat_message_repository
from app.repository.chat_message_attachment import chat_message_attachment_repository


class ChatConversationService:
    """会话业务服务层——封装会话创建、查询、消息持久化等业务逻辑。"""

    async def create_conversation(
        self,
        session: AsyncSession,
        data: ChatConversationCreate,
    ) -> ChatConversation:
        """创建新会话。

        Args:
            session: 数据库会话。
            data: 创建入参（title / user_id / model_code）。

        Returns:
            创建好的 ChatConversation 对象。
        """
        title = data.title or "新对话"
        create_data = {"title": title}
        if data.user_id is not None:
            create_data["user_id"] = data.user_id
        if data.model_code is not None:
            create_data["model_code"] = data.model_code
        _data = await chat_conversation_repository.create(session, create_data)
        return ChatConversationReo.model_validate(_data)

    async def get_conversation_by_id(self, session: AsyncSession, conv_id: str) -> dict:
        """根据会话 ID 查询会话详情。

        Args:
            session: 数据库会话。
            conv_id: 会话 ID。

        Returns:
            会话详情。
        """
        conv = await chat_conversation_repository.get_by_id(session, conv_id)
        if not conv or conv.is_deleted:
            raise BusinessException(code=404, message="会话不存在")
        messages = await chat_message_repository.list_by_conversation(session, conv_id)
        msg_ids = [m.id for m in messages]
        att_map = (
            await chat_message_attachment_repository.list_by_message_ids(
                session, msg_ids
            )
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
        return {**conv_reo.model_dump(), "messages": msg_reos}

    async def get_conversation_list(
        self, session: AsyncSession, query: QueryRequest
    ) -> PageResult[ChatConversationReo]:
        """获取历史会话分页列表。"""

        filters = query.to_repository_filters()

        conversations_list = await chat_conversation_repository.list_paginated(
            session,
            offset=query.offset,
            limit=query.limit,
            **filters,
        )
        total = await chat_conversation_repository.count(session, **filters)
        pages = (total + query.pageSize - 1) // query.pageSize if total > 0 else 0

        return PageResult(
            records=conversations_list,
            total=total,
            page=query.page,
            pageSize=query.pageSize,
            pages=pages,
        )

    async def ensure_conversation(
        self,
        session: AsyncSession,
        conversation_id: str | None = None,
        user_id: str | None = None,
        model_code: str | None = None,
        first_prompt: str | None = None,
    ) -> ChatConversation:
        """确保会话存在——有 ID 就查，查不到或没 ID 就新建。

        新建时如果 first_prompt 不为空，取前 30 字符作为标题。
        如果请求传了不同的 model_code，自动更新会话。

        Args:
            session: 数据库会话。
            conversation_id: 会话 ID，存在时优先查询。
            user_id: 用户 ID。
            model_code: 模型编码。
            first_prompt: 首轮用户 prompt，用于自动生成标题。

        Returns:
            已存在或新创建的 ChatConversation 对象。
        """
        if conversation_id:
            conv = await chat_conversation_repository.get_by_id(
                session, conversation_id
            )
            if conv:
                if model_code and conv.model_code != model_code:
                    await chat_conversation_repository.update_model_code(
                        session, conversation_id, model_code
                    )
                    conv.model_code = model_code
                return conv
        auto_title = None
        if first_prompt:
            auto_title = first_prompt[:10]
        return await self.create_conversation(
            session,
            ChatConversationCreate(
                title=auto_title,
                user_id=user_id,
                model_code=model_code,
            ),
        )

    async def soft_delete_by_id(
        self, session: AsyncSession, conv_id: str
    ) -> ChatConversationReo:
        """根据会话 id 软删除会话。"""
        ok = await chat_conversation_repository.soft_delete(session, conv_id)
        if not ok:
            raise BusinessException(code=404, message="会话不存在")

        conv_updated_data = await chat_conversation_repository.get_by_id(
            session, conv_id
        )
        return ChatConversationReo.model_validate(conv_updated_data)

    async def rename_conversation_by_id(
        self, session: AsyncSession, conv_id: str, data: ChatConversationUpdate
    ) -> ChatConversationReo | None:
        """根据会话 id 重命名会话。"""
        conv = await chat_conversation_repository.get_by_id(session, conv_id)
        if not conv or conv.is_deleted:
            raise BusinessException(code=404, message="会话不存在")
        if not data.title:
            raise BusinessException(code=400, message="标题不能为空")
        ok = await chat_conversation_repository.rename(session, conv_id, data.title)
        if not ok:
            raise BusinessException(code=400, message="重命名失败")
        conv_updated_data = await chat_conversation_repository.get_by_id(
            session, conv_id
        )
        return ChatConversationReo.model_validate(conv_updated_data)

    async def save_user_message(
        self,
        session: AsyncSession,
        conversation_id: str,
        user_content: str,
        model_code: str | None = None,
    ) -> str:
        """流式开始前立即写入 user 消息，保证即使流中断用户消息也能留存。

        Args:
            session: 数据库会话。
            conversation_id: 会话 ID。
            user_content: 用户消息内容。
            model_code: 产生此消息的模型编码（可选）。

        Returns:
            新消息的 ID。
        """
        data = {
            "role": "user",
            "content": user_content,
            "conversation_id": conversation_id,
            "model_code": model_code,
        }
        msg_id = await chat_message_repository.create_one(session, data)
        await chat_conversation_repository.touch_updated_at(session, conversation_id)
        return msg_id

    async def save_assistant_message(
        self,
        session: AsyncSession,
        conversation_id: str,
        assistant_content: str,
        thinking_content: str | None = None,
        tokens_input: int | None = None,
        tokens_output: int | None = None,
        tool_calls: dict | None = None,
        tool_call_id: str | None = None,
        model_code: str | None = None,
    ) -> str:
        """流式正常结束后写入 assistant 消息。

        Args:
            session: 数据库会话。
            conversation_id: 会话 ID。
            assistant_content: 助手消息内容。
            thinking_content: 助手思考链内容（可选）。
            tokens_input: 输入 token 数（可选）。
            tokens_output: 输出 token 数（可选）。
            tool_calls: assistant 消息的 tool_calls JSON（可选）。
            tool_call_id: tool 消息关联的 ID（可选）。
            model_code: 产生此消息的模型编码（可选）。

        Returns:
            新消息的 ID。
        """
        data = {
            "role": "assistant",
            "content": assistant_content,
            "thinking_content": thinking_content,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "conversation_id": conversation_id,
            "model_code": model_code,
        }
        if tool_calls is not None:
            data["tool_calls"] = tool_calls
        if tool_call_id is not None:
            data["tool_call_id"] = tool_call_id
        msg_id = await chat_message_repository.create_one(session, data)
        await chat_conversation_repository.touch_updated_at(session, conversation_id)
        return msg_id

    async def record_message_pair(
        self,
        session: AsyncSession,
        conversation_id: str,
        user_content: str,
        assistant_content: str,
        thinking_content: str | None = None,
        tokens_input: int | None = None,
        tokens_output: int | None = None,
    ) -> None:
        """批量写入一条 user + 一条 assistant 消息，并刷新会话 updated_at。

        Args:
            session: 数据库会话。
            conversation_id: 会话 ID。
            user_content: 用户消息内容。
            assistant_content: 助手消息内容。
            thinking_content: 助手思考链内容（可选）。
            tokens_input: 输入 token 数（可选）。
            tokens_output: 输出 token 数（可选）。
        """
        records = [
            {
                "role": "user",
                "content": user_content,
                "conversation_id": conversation_id,
            },
            {
                "role": "assistant",
                "content": assistant_content,
                "thinking_content": thinking_content,
                "tokens_input": tokens_input,
                "tokens_output": tokens_output,
                "conversation_id": conversation_id,
            },
        ]
        await chat_message_repository.create_batch(session, records)
        await chat_conversation_repository.touch_updated_at(session, conversation_id)


chat_conversation_service = ChatConversationService()
