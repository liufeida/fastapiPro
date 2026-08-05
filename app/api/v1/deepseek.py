import json
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from app.core.exceptions import BusinessException, Execute
from app.services.deepseek import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL,
    ToolEvent,
    deepseek_service,
)
from app.services.file_parser import file_parser

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    prompt: str
    system: Optional[str] = None  # 系统提示词，可选
    thinking: bool = False  # 是否开启思考模式（默认关闭，响应更快）
    stream: bool = True


@router.get(
    "/health", summary="检查 DeepSeek 服务配置", operation_id="deepseekHealthCheck"
)
async def health_check():
    """检查 DeepSeek API Key 是否已配置，并返回当前使用的模型。"""
    if not DEEPSEEK_API_KEY:
        raise BusinessException(code=500, message="DeepSeek API Key 未配置")
    return Execute.response({"status": "ok", "model": DEEPSEEK_MODEL})


@router.post("/chat", summary="非流式对话", operation_id="deepseekChat")
async def chat(request: ChatRequest):
    """非流式接口：一次性返回完整回答。"""
    try:
        result = deepseek_service.chat(
            request.prompt, system=request.system, thinking=request.thinking
        )
        return Execute.response({"response": result})
    except BusinessException:
        raise
    except Exception as e:
        raise BusinessException(code=500, message=f"模型调用失败: {str(e)}")


def _sse(event: str, data: dict) -> ServerSentEvent:
    """构造 SSE 事件，data 统一序列化为 JSON 字符串。

    所有 data 必须是 dict 类型，统一使用 JSON 格式发送，
    避免前端 SSE 解析器的贪婪正则吃掉内容中的空格。
    """
    # 兼容 None 转为空 dict
    if data is None:
        data = {}
    payload = json.dumps(data, ensure_ascii=False)
    return ServerSentEvent(
        raw_data=payload,
        event=event,
        id=uuid.uuid4().hex,
        retry=5000,
    )


@router.post(
    "/chat/stream",
    response_class=EventSourceResponse,
    summary="流式对话（SSE，支持文件上传与联网搜索）",
    operation_id="deepseekChatStream",
)
async def chat_stream(
    prompt: str = Form(..., description="用户问题"),
    system: Optional[str] = Form(None, description="系统提示词，可选"),
    thinking: str = Form("false", description="是否开启思考模式（true/false）"),
    enable_search: bool = Form(False, description="是否开启联网搜索"),
    files: Optional[List[UploadFile]] = File(
        default=None, description="可选，上传的文本类文件"
    ),
):
    """流式接口：支持文件上传与联网搜索。

    - 文件内容会解析后作为上下文拼接到 prompt 前
    - 开启 enable_search 后，模型可通过 web_search 工具获取实时信息
    - 所有 SSE 事件的 data 部分均为 JSON 格式，前端需通过 JSON.parse(e.data) 解析
    - SSE 事件类型及 JSON 结构：
      - thinking: {"reasoning": "思考内容文本"}
      - content: {"content": "生成的内容块"}
      - tool: {"name": "工具名", "args": {...}}
      - tool_result: {"name": "工具名", "result": "执行结果"}
      - Done: {}（空对象）
      - error: {"message": "错误信息", "code": 错误码}
    """
    # 手动解析 thinking 参数（FastAPI Form 的 bool 转换有问题）
    thinking_enabled = thinking.lower() in ("true", "1", "yes")
    logger.info(f"接收到请求: prompt={prompt[:50]}..., thinking={thinking} -> {thinking_enabled}, enable_search={enable_search}")

    try:
        # 解析上传的文件（若有）
        file_context = await file_parser.parse_many(files) if files else None

        async for chunk in deepseek_service.chat_stream_with_tools(
            prompt=prompt,
            system=system,
            thinking=thinking_enabled,
            enable_search=enable_search,
            file_context=file_context,
        ):
            if isinstance(chunk, ToolEvent):
                # 工具事件
                if chunk.type == "tool":
                    yield _sse(
                        "tool",
                        {"name": chunk.name, "args": chunk.args or {}},
                    )
                elif chunk.type == "tool_result":
                    yield _sse(
                        "tool_result",
                        {"name": chunk.name, "result": chunk.result or ""},
                    )
                elif chunk.type == "thinking":
                    # 思考内容事件
                    yield _sse(
                        "thinking",
                        {"reasoning": chunk.result or ""},
                    )
            else:
                # 内容块：将内容放在 JSON 字段中
                yield _sse("content", {"content": chunk})

        yield _sse("Done", {})
    except BusinessException as e:
        yield _sse("error", {"message": e.message, "code": e.code})
    except Exception as e:
        yield _sse("error", {"message": f"[错误: {str(e)}]"})
