import asyncio
import json
import uuid
from typing import AsyncIterable

import httpx
from fastapi import APIRouter
from fastapi.sse import EventSourceResponse, ServerSentEvent
from ollama import Client
from pydantic import BaseModel

from app.core.exceptions import BusinessException, Execute

router = APIRouter()

OLLAMA_HOST = "http://localhost:11434"
MODEL_NAME = "deepseek-r1:8b"

CLOUD_OLLAMA_URL = "https://ollama.com"
CLOUD_MODEL_NAME = "deepseek-v3.1:671b-cloud"
OLLAMA_API_KEY = "479ca30ba86f48dca81b55c7c6932f1a.amtD5Lfezf45TgZ26BPXF5Hq"
ollama_client = Client(host=OLLAMA_HOST)


def _get_headers() -> dict[str, str]:
    if not OLLAMA_API_KEY:
        raise BusinessException(code=500, detail="Ollama Cloud API Key is not set.")
    return {
        "Authorization": f"Bearer {OLLAMA_API_KEY}",
        "Content-Type": "application/json",
    }


class ChatRequest(BaseModel):
    prompt: str
    stream: bool = True


@router.get(
    "/health", summary="检查 Ollama 服务可用性", operation_id="ollamaHealthCheck"
)
async def health_check():
    """检查本地 Ollama 服务是否可用。"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{OLLAMA_HOST}/api/tags")
            if response.status_code == 200:
                return Execute.response({"status": "ok", "ollama": "connected"})
    except Exception:
        pass
    raise BusinessException(code=503, detail="Ollama 服务不可用")


@router.post("/chat", summary="非流式对话", operation_id="ollamaChat")
async def chat(request: ChatRequest):
    """非流式接口：一次性返回完整回答。"""
    try:
        response = ollama_client.generate(
            model=MODEL_NAME, prompt=request.prompt, stream=False
        )
        return {"response": response["response"].strip()}
    except Exception as e:
        raise BusinessException(code=500, detail=f"模型调用失败: {str(e)}")


@router.post(
    "/chat/stream",
    response_class=EventSourceResponse,
    summary="流式对话（调用 Ollama 云服务）",
    operation_id="ollamaChatStream",
)
async def chat_stream(request: ChatRequest) -> AsyncIterable[ServerSentEvent]:
    payload = {
        "model": CLOUD_MODEL_NAME,
        "prompt": request.prompt,
        "stream": True,
    }
    try:
        # 不用 async with，需要手动 await client.aclose()，否则连接池不会被清理，长时间运行可能导致资源耗尽
        # 创建一个异步 HTTP 客户端实例，并在代码块结束时自动关闭客户端
        async with httpx.AsyncClient(timeout=120.0) as client:
            # 发起一个流式 HTTP 请求，并在代码块结束时自动关闭响应流
            async with client.stream(
                "POST",
                f"{CLOUD_OLLAMA_URL}/api/generate",
                json=payload,
                headers=_get_headers(),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if chunk.get("response"):
                        await asyncio.sleep(1)
                        yield ServerSentEvent(
                            raw_data=chunk["response"],
                            event="content",
                            id=uuid.uuid4().hex,
                            retry=5000,
                        )

                yield ServerSentEvent(
                    raw_data=None,
                    event="Done",
                    id=uuid.uuid4().hex,
                    retry=5000,
                )
    except Exception as e:
        yield ServerSentEvent(raw_data=f"[错误: {str(e)}]", event="error")
