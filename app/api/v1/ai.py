import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import AsyncIterator, List, Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.dependencies import SessionDeep
from app.core.exceptions import BusinessException, Execute
from app.services.ai.base import StreamEvent, ToolEvent
from app.services.ai.dispatcher import ai_dispatcher
from app.services.ai.registry import provider_registry
from app.services.ai.sse import build_sse
from app.services.chat_conversation import chat_conversation_service
from app.services.file_parser import file_parser

logger = logging.getLogger(__name__)

router = APIRouter()

_CHUNK_IDLE_TIMEOUT = 180.0


async def _iter_with_chunk_timeout(aiter: AsyncIterator, per_chunk_timeout: float):
    """迭代 async iterator，每个 chunk 独立超时保护。"""
    aiter = aiter.__aiter__()
    loop = asyncio.get_running_loop()
    while True:
        next_task = loop.create_task(aiter.__anext__())
        try:
            item = await asyncio.wait_for(next_task, timeout=per_chunk_timeout)
            yield item
        except asyncio.TimeoutError:
            next_task.cancel()
            raise
        except StopAsyncIteration:
            break


class ChatRequest(BaseModel):
    """通用非流式对话请求。"""
    model: str  # model_code
    prompt: str
    system: Optional[str] = None
    thinking: bool = False
    prompt_code: Optional[str] = None
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None


@router.get(
    "/health",
    summary="检查 AI 平台配置",
    operation_id="aiHealthCheck",
)
async def health_check(session: SessionDeep):
    """返回已注册的 provider 列表与启用模型数量。"""
    from app.repository.ai_model_config import ai_model_config_repository

    providers = provider_registry.list_providers()
    enabled_models = await ai_model_config_repository.list_enabled(session)
    return Execute.response({
        "status": "ok",
        "providers": providers,
        "enabled_count": len(enabled_models),
    })


@router.post(
    "/chat",
    summary="通用非流式对话",
    operation_id="aiChat",
)
async def chat(session: SessionDeep, request: ChatRequest):
    """通用非流式对话，根据 model 路由到对应 Provider。"""
    try:
        conv = None
        if request.conversation_id or True:
            conv = await chat_conversation_service.ensure_conversation(
                session,
                conversation_id=request.conversation_id,
                user_id=request.user_id,
                model_code=request.model,
                first_prompt=request.prompt[:30],
            )

        await chat_conversation_service.save_user_message(
            session,
            conversation_id=conv.id,
            user_content=request.prompt,
            model_code=request.model,
        )

        result = await ai_dispatcher.chat(
            session,
            model_code=request.model,
            prompt=request.prompt,
            system=request.system,
            thinking=request.thinking,
            prompt_code=request.prompt_code,
            conversation_id=conv.id,
        )

        try:
            await chat_conversation_service.save_assistant_message(
                session,
                conversation_id=conv.id,
                assistant_content=result,
                thinking_content=None,
                model_code=request.model,
            )
        except Exception as persist_err:
            logger.warning(f"assistant 消息持久化失败: {persist_err}")

        return Execute.response({"response": result, "conversation_id": conv.id})
    except BusinessException:
        raise
    except Exception as e:
        raise BusinessException(code=500, message=f"模型调用失败: {str(e)}")


@router.post(
    "/chat/stream",
    response_class=StreamingResponse,
    summary="通用流式对话（SSE，支持文件上传与联网搜索）",
    operation_id="aiChatStream",
    responses={200: {"description": "SSE event stream", "content": {"text/event-stream": {}}}},
)
async def chat_stream(
    session: SessionDeep,
    model: str = Form(..., description="模型代码 model_code"),
    prompt: str = Form(..., description="用户问题"),
    system: Optional[str] = Form(None, description="系统提示词，可选"),
    thinking: str = Form("false", description="是否开启思考模式（true/false）"),
    enable_search: bool = Form(False, description="是否开启联网搜索"),
    prompt_code: Optional[str] = Form(None, description="可选的自定义提示词 code，需为非绑定、非全局默认的启用提示词"),
    conversation_id: Optional[str] = Form(None, description="可选，已有会话 ID；不传则自动创建新会话"),
    user_id: Optional[str] = Form(None),
    attachment_ids: Optional[str] = Form(None, description="可选，附件 ID 数组 JSON 字符串，挂载在 user 消息上"),
    files: Optional[List[UploadFile]] = File(default=None, description="可选，上传的文本类文件"),
):
    """通用流式对话：根据 model 路由到对应 Provider，输出统一 SSE 事件流。

    SSE 事件类型及 JSON 结构：
    - start:          {"request_id": ..., "model": ..., "thinking": ..., "enable_search": ...}
    - thinking_start: {"timestamp": ...}
    - thinking:       {"reasoning": "思考内容增量文本"}
    - thinking_end:   {"reasoning": "完整思考内容", "total_chars": N}
    - content_start:  {"timestamp": ...}
    - content:        {"content": "生成的内容增量块"}
    - content_end:    {"content": "完整内容", "total_chars": N}
    - tool_start:     {"tool_call_id": ..., "name": "工具名", "args": {...}}
    - tool:           {"name": "工具名", "args": {...}}（向后兼容）
    - tool_result:    {"tool_call_id": ..., "name": "工具名", "result": "...", "elapsed_ms": N}
    - usage:          {"prompt_tokens": ..., "completion_tokens": ..., "total_tokens": ...}
    - end:            {"request_id": ..., "stop_reason": "stop/error", "elapsed_ms": N}
    - Done:           {}（向后兼容）
    - error:          {"message": "错误信息", "code": 错误码}
    """
    thinking_enabled = thinking.lower() in ("true", "1", "yes")
    logger.info(
        f"AI 流式请求: model={model}, prompt={prompt[:50]}..., "
        f"thinking={thinking} -> {thinking_enabled}, enable_search={enable_search}"
    )

    config = None

    file_context = await file_parser.parse_many(files) if files else None

    conv = await chat_conversation_service.ensure_conversation(
        session,
        conversation_id=conversation_id,
        user_id=user_id,
        model_code=model,
        first_prompt=prompt[:30],
    )
    conv_id = conv.id

    user_msg_id = await chat_conversation_service.save_user_message(
        session,
        conversation_id=conv_id,
        user_content=prompt,
        model_code=model,
    )

    if attachment_ids:
        try:
            ids = json.loads(attachment_ids)
            if isinstance(ids, list) and ids:
                from app.repository.chat_message_attachment import chat_message_attachment_repository
                for fid in ids:
                    try:
                        await chat_message_attachment_repository.create(session, {
                            "message_id": user_msg_id,
                            "file_id": fid,
                            "url": "",
                            "filename": "",
                            "content_type": "",
                            "type": "file",
                        })
                    except Exception as att_err:
                        logger.warning(f"附件关联失败 file_id={fid}: {att_err}")
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"attachment_ids 格式错误: {attachment_ids}")

    async def _event_generator():
        import uuid

        request_id = uuid.uuid4().hex
        start_time = datetime.now(timezone.utc)

        thinking_parts: list[str] = []
        content_parts: list[str] = []
        thinking_started = False
        content_started = False
        thinking_ended = False
        content_ended = False
        usage_data = {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "reasoning_tokens": None,
        }

        yield build_sse("start", {
            "request_id": request_id,
            "model": model,
            "model_name": getattr(config, "model_name", model) if config else model,
            "thinking": thinking_enabled,
            "enable_search": enable_search,
            "timestamp": start_time.isoformat(),
            "conversation_id": conv_id,
        })

        def _finish_thinking():
            nonlocal thinking_started, thinking_ended
            if thinking_started and not thinking_ended:
                full = "".join(thinking_parts)
                thinking_ended = True
                yield build_sse("thinking_end", {
                    "reasoning": full,
                    "total_chars": len(full),
                })

        def _finish_content():
            nonlocal content_started, content_ended
            if content_started and not content_ended:
                full = "".join(content_parts)
                content_ended = True
                yield build_sse("content_end", {
                    "content": full,
                    "total_chars": len(full),
                })

        try:
            async for chunk in _iter_with_chunk_timeout(
                ai_dispatcher.chat_stream_with_tools(
                    session,
                    model_code=model,
                    prompt=prompt,
                    system=system,
                    thinking=thinking_enabled,
                    enable_search=enable_search,
                    file_context=file_context,
                    _config=config,
                    prompt_code=prompt_code,
                    conversation_id=conv_id,
                ),
                per_chunk_timeout=_CHUNK_IDLE_TIMEOUT,
            ):
                if isinstance(chunk, StreamEvent):
                    if chunk.type == "thinking":
                        for _x in _finish_content():
                            yield _x
                        if not thinking_started:
                            thinking_started = True
                            yield build_sse("thinking_start", {
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            })
                        text = chunk.reasoning or chunk.result or ""
                        thinking_parts.append(text)
                        yield build_sse("thinking", {"reasoning": text})

                    elif chunk.type == "tool_start":
                        for _x in _finish_content():
                            yield _x
                        for _x in _finish_thinking():
                            yield _x
                        yield build_sse("tool_start", {
                            "tool_call_id": chunk.tool_call_id or "",
                            "name": chunk.name or "",
                            "args": chunk.args or {},
                        })
                        yield build_sse("tool", {
                            "name": chunk.name or "",
                            "args": chunk.args or {},
                        })

                    elif chunk.type == "tool_result":
                        yield build_sse("tool_result", {
                            "tool_call_id": chunk.tool_call_id or "",
                            "name": chunk.name or "",
                            "result": chunk.result or "",
                            "elapsed_ms": chunk.elapsed_ms or 0,
                        })
                        content_started = False
                        content_ended = False
                        content_parts.clear()

                    elif chunk.type == "usage":
                        usage_data = {
                            "prompt_tokens": chunk.prompt_tokens,
                            "completion_tokens": chunk.completion_tokens,
                            "total_tokens": chunk.total_tokens,
                            "reasoning_tokens": chunk.reasoning_tokens,
                        }

                else:
                    for _x in _finish_thinking():
                        yield _x
                    if not content_started:
                        content_started = True
                        yield build_sse("content_start", {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                    content_parts.append(chunk)
                    yield build_sse("content", {"content": chunk})

            for _x in _finish_content():
                yield _x
            for _x in _finish_thinking():
                yield _x

            yield build_sse("usage", usage_data)

            elapsed_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            yield build_sse("end", {
                "stop_reason": "stop",
                "request_id": request_id,
                "elapsed_ms": elapsed_ms,
            })

            try:
                await chat_conversation_service.save_assistant_message(
                    session,
                    conversation_id=conv_id,
                    assistant_content="".join(content_parts),
                    thinking_content="".join(thinking_parts) or None,
                    tokens_input=usage_data.get("prompt_tokens"),
                    tokens_output=usage_data.get("completion_tokens"),
                    model_code=model,
                )
            except Exception as persist_err:
                logger.warning(f"assistant 消息持久化失败: {persist_err}")

            yield build_sse("Done", {})

        except asyncio.TimeoutError:
            logger.warning(f"AI 流式对话超时: model={model}, idle_timeout={_CHUNK_IDLE_TIMEOUT}s")
            for _x in _finish_content():
                yield _x
            for _x in _finish_thinking():
                yield _x
            yield build_sse("error", {"message": "模型请求超时，请重试", "code": 504})
            elapsed_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            yield build_sse("end", {
                "stop_reason": "error",
                "request_id": request_id,
                "elapsed_ms": elapsed_ms,
            })
            yield build_sse("Done", {})
        except BusinessException as e:
            for _x in _finish_content():
                yield _x
            for _x in _finish_thinking():
                yield _x
            yield build_sse("error", {"message": e.message, "code": e.code})
            elapsed_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            yield build_sse("end", {
                "stop_reason": "error",
                "request_id": request_id,
                "elapsed_ms": elapsed_ms,
            })
            yield build_sse("Done", {})
        except Exception as e:
            logger.exception("AI 流式对话异常")
            for _x in _finish_content():
                yield _x
            for _x in _finish_thinking():
                yield _x
            yield build_sse("error", {"message": f"[错误: {str(e)}]"})
            elapsed_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
            yield build_sse("end", {
                "stop_reason": "error",
                "request_id": request_id,
                "elapsed_ms": elapsed_ms,
            })
            yield build_sse("Done", {})

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
