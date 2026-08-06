import logging
from typing import List, Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.dependencies import SessionDeep
from app.core.exceptions import BusinessException, Execute
from app.services.ai.base import ToolEvent
from app.services.ai.dispatcher import ai_dispatcher
from app.services.ai.registry import provider_registry
from app.services.ai.sse import build_sse
from app.services.file_parser import file_parser

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    """通用非流式对话请求。"""
    model: str  # model_code
    prompt: str
    system: Optional[str] = None
    thinking: bool = False


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
        result = await ai_dispatcher.chat(
            session,
            model_code=request.model,
            prompt=request.prompt,
            system=request.system,
            thinking=request.thinking,
        )
        return Execute.response({"response": result})
    except BusinessException:
        raise
    except Exception as e:
        raise BusinessException(code=500, message=f"模型调用失败: {str(e)}")


@router.post(
    "/chat/stream",
    summary="通用流式对话（SSE，支持文件上传与联网搜索）",
    operation_id="aiChatStream",
)
async def chat_stream(
    session: SessionDeep,
    model: str = Form(..., description="模型代码 model_code"),
    prompt: str = Form(..., description="用户问题"),
    system: Optional[str] = Form(None, description="系统提示词，可选"),
    thinking: str = Form("false", description="是否开启思考模式（true/false）"),
    enable_search: bool = Form(False, description="是否开启联网搜索"),
    files: Optional[List[UploadFile]] = File(default=None, description="可选，上传的文本类文件"),
):
    """通用流式对话：根据 model 路由到对应 Provider，输出统一 SSE 事件流。

    SSE 事件类型及 JSON 结构：
    - thinking: {"reasoning": "思考内容文本"}
    - content: {"content": "生成的内容块"}
    - tool: {"name": "工具名", "args": {...}}
    - tool_result: {"name": "工具名", "result": "执行结果"}
    - Done: {}（空对象）
    - error: {"message": "错误信息", "code": 错误码}
    """
    thinking_enabled = thinking.lower() in ("true", "1", "yes")
    logger.info(
        f"AI 流式请求: model={model}, prompt={prompt[:50]}..., "
        f"thinking={thinking} -> {thinking_enabled}, enable_search={enable_search}"
    )

    config = await ai_dispatcher.resolve(session, model)
    ai_dispatcher.check_capability(config, thinking_enabled, enable_search)

    file_context = await file_parser.parse_many(files) if files else None

    async def _event_generator():
        _total = _reason = _content = _tool = 0
        try:
            async for chunk in ai_dispatcher.chat_stream_with_tools(
                session,
                model_code=model,
                prompt=prompt,
                system=system,
                thinking=thinking_enabled,
                enable_search=enable_search,
                file_context=file_context,
                _config=config,
            ):
                _total += 1
                if isinstance(chunk, ToolEvent):
                    if chunk.type == "tool":
                        _tool += 1
                        yield build_sse("tool", {"name": chunk.name, "args": chunk.args or {}})
                    elif chunk.type == "tool_result":
                        _tool += 1
                        yield build_sse("tool_result", {"name": chunk.name, "result": chunk.result or ""})
                    elif chunk.type == "thinking":
                        _reason += 1
                        yield build_sse("thinking", {"reasoning": chunk.result or ""})
                else:
                    _content += 1
                    yield build_sse("content", {"content": chunk})
            logger.info(f"SSE yield 统计 total={_total} reason={_reason} content={_content} tool={_tool}")
            yield build_sse("Done", {})
        except BusinessException as e:
            yield build_sse("error", {"message": e.message, "code": e.code})
        except Exception as e:
            logger.exception("AI 流式对话异常")
            yield build_sse("error", {"message": f"[错误: {str(e)}]"})

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
