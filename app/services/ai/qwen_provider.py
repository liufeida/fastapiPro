import json
import logging
from typing import AsyncIterator, Optional

import httpx
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI

from app.core.exceptions import BusinessException
from app.services.ai.base import AIProvider, StreamChunk, ToolEvent
from app.services.ai.registry import provider_registry
from app.services.web_search import do_search, web_search

logger = logging.getLogger(__name__)


_HTTPX_STREAM_TIMEOUT = httpx.Timeout(
    connect=30.0,
    read=None,        # streaming 模式下不做 chunk 间隔超时（模型 thinking 阶段可能长时间无数据）
    write=30.0,
    pool=30.0,
)


class QwenProvider(AIProvider):
    """阿里云通义千问模型 Provider（DashScope OpenAI 兼容端点）。

    thinking=false: 走 LangChain ChatOpenAI
    thinking=true: 走原生 httpx 直接消费 SSE 流（避免 LangChain 清除 reasoning_content）
    """

    def _build_messages(self, prompt, system, file_context=None):
        final_prompt = prompt
        if file_context:
            final_prompt = f"【文件上下文】\n{file_context}\n\n【用户问题】\n{prompt}"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": final_prompt})
        return messages

    def _to_langchain_messages(self, dict_messages) -> list[BaseMessage]:
        result: list[BaseMessage] = []
        for msg in dict_messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "system":
                result.append(SystemMessage(content=content))
            elif role == "user":
                result.append(HumanMessage(content=content))
        return result

    def _to_dict_messages(self, langchain_messages) -> list[dict]:
        result: list[dict] = []
        for msg in langchain_messages:
            if isinstance(msg, SystemMessage):
                result.append({"role": "system", "content": msg.content})
            elif isinstance(msg, HumanMessage):
                result.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                entry: dict = {"role": "assistant", "content": msg.content or ""}
                tool_calls = msg.tool_calls or []
                if tool_calls:
                    formatted = []
                    for tc in tool_calls:
                        formatted.append(
                            {
                                "id": tc.get("id", ""),
                                "type": "function",
                                "function": {
                                    "name": tc.get("name", ""),
                                    "arguments": json.dumps(
                                        tc.get("args", {}), ensure_ascii=False
                                    ),
                                },
                            }
                        )
                    entry["tool_calls"] = formatted
                result.append(entry)
            elif isinstance(msg, ToolMessage):
                result.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg.tool_call_id,
                        "content": msg.content,
                    }
                )
            else:
                result.append(
                    {"role": "user", "content": getattr(msg, "content", "")}
                )
        return result

    def _get_llm(self, config, streaming=False, thinking=False) -> ChatOpenAI:
        if not config.api_key:
            raise BusinessException(code=500, message="Qwen API Key 未配置")
        extra_body = {"enable_thinking": True} if thinking else {"enable_thinking": False}
        return ChatOpenAI(
            model=config.model_code,
            api_key=config.api_key,
            base_url=(
                config.base_url
                or "https://dashscope.aliyuncs.com/compatible-mode/v1"
            ),
            temperature=(
                config.temperature if config.temperature is not None else 0.7
            ),
            streaming=streaming,
            extra_body=extra_body,
        )

    async def _stream_raw(
        self, config, messages, thinking=False
    ) -> AsyncIterator[StreamChunk]:
        """原生 httpx 流式：直接消费 DashScope SSE，提取 reasoning_content。

        先完整收集所有 chunk（确保 httpx 请求完整结束），再逐个 yield，
        避免嵌套 async generator 中 httpx 连接被 yield 暂停意外关闭。
        """
        url = (
            config.base_url
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).rstrip("/")
        url = f"{url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "model": config.model_code,
            "messages": messages,
            "stream": True,
        }
        if thinking:
            payload["enable_thinking"] = True

        collected: list[StreamChunk] = []
        done_seen = False
        try:
            async with httpx.AsyncClient(timeout=_HTTPX_STREAM_TIMEOUT) as client:
                async with client.stream(
                    "POST", url, json=payload, headers=headers
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[len("data:") :].strip()
                        if data_str == "[DONE]":
                            done_seen = True
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        reasoning = delta.get("reasoning_content")
                        if reasoning:
                            collected.append(
                                ToolEvent(type="thinking", name="reasoning", result=reasoning)
                            )
                        content = delta.get("content")
                        if content is not None:
                            collected.append(content)
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning(f"_stream_raw httpx 异常 thinking={thinking}: {type(exc).__name__}: {exc}")
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            logger.info(f"_stream_raw 客户端断开 thinking={thinking}: {exc}")
        finally:
            if not done_seen:
                logger.warning(
                    f"_stream_raw 未收到 [DONE] thinking={thinking} "
                    f"收集 chunks={len(collected)}"
                )

        for chunk in collected:
            yield chunk

    @staticmethod
    def _extract_reasoning(chunk: AIMessage) -> Optional[str]:
        return chunk.additional_kwargs.get("reasoning_content")

    async def chat(
        self, config, prompt: str, system: Optional[str] = None, thinking: bool = False
    ) -> str:
        messages = self._build_messages(prompt, system)
        if thinking:
            parts: list[str] = []
            async for chunk in self._stream_raw(config, messages, thinking=True):
                if isinstance(chunk, str):
                    parts.append(chunk)
            return "".join(parts)
        llm = self._get_llm(config, streaming=False, thinking=False)
        lc_messages = self._to_langchain_messages(messages)
        response = llm.invoke(lc_messages)
        return response.content

    async def chat_stream(
        self,
        config,
        prompt: str,
        system: Optional[str] = None,
        thinking: bool = False,
    ) -> AsyncIterator[StreamChunk]:
        messages = self._build_messages(prompt, system)
        if thinking:
            async for chunk in self._stream_raw(config, messages, thinking=True):
                yield chunk
            return
        llm = self._get_llm(config, streaming=True, thinking=False)
        lc_messages = self._to_langchain_messages(messages)
        async for chunk in llm.astream(lc_messages):
            reasoning = self._extract_reasoning(chunk)
            if reasoning:
                yield ToolEvent(type="thinking", name="reasoning", result=reasoning)
            if chunk.content:
                yield chunk.content

    async def chat_stream_with_tools(
        self,
        config,
        prompt: str,
        system: Optional[str] = None,
        thinking: bool = False,
        enable_search: bool = False,
        file_context: Optional[str] = None,
    ) -> AsyncIterator[StreamChunk]:
        messages = self._build_messages(prompt, system, file_context)

        if not enable_search:
            if thinking:
                async for chunk in self._stream_raw(config, messages, thinking=True):
                    yield chunk
            else:
                llm = self._get_llm(config, streaming=True, thinking=False)
                lc_messages = self._to_langchain_messages(messages)
                async for chunk in llm.astream(lc_messages):
                    reasoning = self._extract_reasoning(chunk)
                    if reasoning:
                        yield ToolEvent(
                            type="thinking", name="reasoning", result=reasoning
                        )
                    if chunk.content:
                        yield chunk.content
            return

        lc_messages = self._to_langchain_messages(messages)
        llm = self._get_llm(config, streaming=False, thinking=False)
        llm_with_tools = llm.bind_tools([web_search])

        for _ in range(3):
            accumulated: AIMessage = await llm_with_tools.ainvoke(lc_messages)
            tool_calls = accumulated.tool_calls

            if not tool_calls:
                if thinking:
                    dict_messages = self._to_dict_messages(lc_messages)
                    async for chunk in self._stream_raw(
                        config, dict_messages, thinking=True
                    ):
                        yield chunk
                else:
                    async for chunk in llm_with_tools.astream(lc_messages):
                        reasoning = self._extract_reasoning(chunk)
                        if reasoning:
                            yield ToolEvent(
                                type="thinking",
                                name="reasoning",
                                result=reasoning,
                            )
                        if chunk.content:
                            yield chunk.content
                return

            reasoning = self._extract_reasoning(accumulated)
            if reasoning:
                yield ToolEvent(type="thinking", name="reasoning", result=reasoning)
            if accumulated.content:
                yield accumulated.content

            lc_messages.append(accumulated)

            for tool_call in tool_calls:
                tool_name = tool_call.get("name", "")
                tool_args = tool_call.get("args", {})
                tool_id = tool_call.get("id", "")

                yield ToolEvent(type="tool", name=tool_name, args=tool_args)

                if tool_name == "web_search":
                    query = tool_args.get("query", "")
                    result = do_search(query)
                else:
                    result = f"未知工具: {tool_name}"

                yield ToolEvent(type="tool_result", name=tool_name, result=result)

                lc_messages.append(
                    ToolMessage(content=result, tool_call_id=tool_id)
                )

        # 循环耗尽（3 次工具调用用完）：强制让模型输出最终回答
        logger.warning("工具调用循环耗尽，强制让模型输出最终回答")
        if thinking:
            dict_messages = self._to_dict_messages(lc_messages)
            async for chunk in self._stream_raw(config, dict_messages, thinking=True):
                yield chunk
        else:
            async for chunk in llm_with_tools.astream(lc_messages):
                reasoning = self._extract_reasoning(chunk)
                if reasoning:
                    yield ToolEvent(
                        type="thinking",
                        name="reasoning",
                        result=reasoning,
                    )
                if chunk.content:
                    yield chunk.content


provider_registry.register("qwen", QwenProvider())
