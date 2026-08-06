import json
import logging
from typing import AsyncIterator, Optional

import httpx

from app.services.ai.base import AIProvider, StreamChunk, StreamEvent
from app.services.ai.registry import provider_registry

logger = logging.getLogger(__name__)


class OllamaProvider(AIProvider):
    """Ollama 模型 Provider。

    不支持 thinking 模式与工具调用（由 dispatcher 拦截）。
    支持本地部署与云端 API 两种模式（通过 extra_config 区分）。
    """

    def _resolve_endpoint(self, config):
        """根据 config 解析请求 URL 与 headers。

        - 云端模式：extra_config 含 cloud_url + cloud_api_key，调云端 API
        - 本地模式：调 base_url/api/generate，无需鉴权
        """
        extra = config.extra_config or {}
        cloud_url = extra.get("cloud_url")
        cloud_api_key = extra.get("cloud_api_key")

        if cloud_url and cloud_api_key:
            # 云端模式
            url = f"{cloud_url.rstrip('/')}/api/generate"
            headers = {
                "Authorization": f"Bearer {cloud_api_key}",
                "Content-Type": "application/json",
            }
        else:
            # 本地模式
            base = (config.base_url or "http://localhost:11434").rstrip("/")
            url = f"{base}/api/generate"
            headers = {"Content-Type": "application/json"}

        return url, headers

    async def chat(self, config, prompt: str, system: Optional[str] = None, thinking: bool = False) -> str:
        """非流式对话：调用 Ollama generate 接口，stream=False。"""
        url, headers = self._resolve_endpoint(config)
        final_prompt = prompt
        if system:
            final_prompt = f"【系统提示】{system}\n\n【用户问题】{prompt}"
        payload = {
            "model": config.model_code,
            "prompt": final_prompt,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()

    async def chat_stream(self, config, prompt: str, system: Optional[str] = None, thinking: bool = False) -> AsyncIterator[StreamChunk]:
        """流式对话：逐块 yield 内容字符串，末尾追加 usage 事件。"""
        url, headers = self._resolve_endpoint(config)
        final_prompt = prompt
        if system:
            final_prompt = f"【系统提示】{system}\n\n【用户问题】{prompt}"
        payload = {
            "model": config.model_code,
            "prompt": final_prompt,
            "stream": True,
        }
        collected: list[StreamChunk] = []
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    content = chunk.get("response")
                    if content:
                        collected.append(content)

        collected.append(StreamEvent(
            type="usage",
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
        ))

        for chunk in collected:
            yield chunk

    async def chat_stream_with_tools(self, config, prompt: str, system: Optional[str] = None, thinking: bool = False, enable_search: bool = False, file_context: Optional[str] = None) -> AsyncIterator[StreamChunk]:
        """Ollama 不支持工具调用，直接退化为 chat_stream。

        若 enable_search=True，dispatcher 会拦截报错，不会走到这里。
        """
        final_prompt = prompt
        if file_context:
            final_prompt = f"【文件上下文】\n{file_context}\n\n【用户问题】\n{prompt}"
        async for chunk in self.chat_stream(config, final_prompt, system, thinking):
            yield chunk


# 模块加载时注册
provider_registry.register("ollama", OllamaProvider())
