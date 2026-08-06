import json
import logging
import time
from typing import AsyncIterator, Optional

import httpx
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_deepseek import ChatDeepSeek

from app.core.exceptions import BusinessException
from app.services.ai.base import AIProvider, StreamChunk, StreamEvent
from app.services.ai.registry import provider_registry
from app.services.web_search import do_search, web_search

logger = logging.getLogger(__name__)


_HTTPX_STREAM_TIMEOUT = httpx.Timeout(
    connect=30.0,
    read=None,        # streaming 模式下不做 chunk 间隔超时（模型 thinking 阶段可能长时间无数据）
    write=30.0,
    pool=30.0,
)


class DeepSeekProvider(AIProvider):
    """DeepSeek 模型 Provider。

    thinking=false: 走 LangChain ChatDeepSeek
    thinking=true: 走原生 httpx 直接消费 SSE 流（避免 LangChain 清除 reasoning_content）
    """

    def _build_messages(self, prompt, system, file_context=None):
        """组装消息列表（dict 格式，供 _stream_raw 使用）。"""
        final_prompt = prompt
        if file_context:
            final_prompt = f"【文件上下文】\n{file_context}\n\n【用户问题】\n{prompt}"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": final_prompt})
        return messages

    def _to_langchain_messages(self, dict_messages) -> list[BaseMessage]:
        """将 dict 消息列表转换为 LangChain BaseMessage 列表（仅处理 system/user）。"""
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
        """将 LangChain BaseMessage 列表转换为 dict 格式（供 _stream_raw 使用）。

        支持 SystemMessage / HumanMessage / AIMessage(含 tool_calls) / ToolMessage。
        """
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

    def _get_llm(self, config, streaming=False, thinking=False) -> ChatDeepSeek:
        """创建 ChatDeepSeek 实例。"""
        if not config.api_key:
            raise BusinessException(code=500, message="DeepSeek API Key 未配置")
        extra_body = (
            {"thinking": {"type": "enabled"}}
            if thinking
            else {"thinking": {"type": "disabled"}}
        )
        return ChatDeepSeek(
            model=config.model_code,
            api_key=config.api_key,
            base_url=config.base_url or "https://api.deepseek.com",
            temperature=(
                config.temperature if config.temperature is not None else 0.7
            ),
            streaming=streaming,
            extra_body=extra_body,
        )

    async def _stream_raw(
        self, config, messages, thinking=False
    ) -> AsyncIterator[StreamChunk]:
        """原生 httpx 流式：直接消费模型 SSE，提取 reasoning_content。

        thinking=true 时必须走此方法（LangChain 会清除 reasoning_content 字段）。
        使用 read=None 超时——thinking 模式下 reasoning→content 之间可能有长时间间隔。

        先完整收集所有 chunk（确保 httpx 请求完整结束），再逐个 yield，
        避免嵌套 async generator 中 httpx 连接被 yield 暂停意外关闭。
        """
        url = (config.base_url or "https://api.deepseek.com").rstrip("/")
        url = f"{url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": config.model_code,
            "messages": messages,
            "stream": True,
        }
        if thinking:
            payload["thinking"] = {"type": "enabled"}

        collected: list[StreamChunk] = []
        last_raw_chunk = None
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
                        last_raw_chunk = chunk
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        reasoning = delta.get("reasoning_content")
                        if reasoning:
                            collected.append(
                                StreamEvent(type="thinking", reasoning=reasoning)
                            )
                        content = delta.get("content")
                        if content is not None:
                            collected.append(content)
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning(
                f"_stream_raw httpx 异常 thinking={thinking}: "
                f"{type(exc).__name__}: {exc}"
            )
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            logger.info(f"_stream_raw 客户端断开 thinking={thinking}: {exc}")
        finally:
            if not done_seen:
                logger.warning(
                    f"_stream_raw 未收到 [DONE] thinking={thinking} "
                    f"收集 chunks={len(collected)}"
                )

        if last_raw_chunk:
            usage = last_raw_chunk.get("usage", {}) or {}
            if usage:
                collected.append(StreamEvent(
                    type="usage",
                    prompt_tokens=usage.get("prompt_tokens"),
                    completion_tokens=usage.get("completion_tokens"),
                    total_tokens=usage.get("total_tokens"),
                ))

        for chunk in collected:
            yield chunk

    @staticmethod
    def _extract_reasoning(chunk: AIMessage) -> Optional[str]:
        """从 AIMessageChunk 中提取 reasoning_content（LangChain 路径用）。"""
        return chunk.additional_kwargs.get("reasoning_content")

    async def chat(
        self, config, prompt: str, system: Optional[str] = None, thinking: bool = False
    ) -> str:
        """非流式对话，返回完整回复。"""
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
        """流式对话，逐块返回内容。开启 thinking 时会先输出思考内容。"""
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
                yield StreamEvent(type="thinking", reasoning=reasoning)
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
        """增强版流式对话：支持文件上下文与联网搜索工具调用循环。

        - enable_search=False: 退化为 chat_stream
        - enable_search=True: LangChain bind_tools 工具循环
        - 工具循环耗尽后强制输出最终回答，确保 SSE 流完整
        """
        messages = self._build_messages(prompt, system, file_context)

        # 关闭搜索：退化为纯流式
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
                        yield StreamEvent(type="thinking", reasoning=reasoning)
                    if chunk.content:
                        yield chunk.content
            return

        # 开启搜索：绑定 web_search 工具
        # 工具循环用 LangChain（thinking=false，不依赖 reasoning_content）
        lc_messages = self._to_langchain_messages(messages)
        llm = self._get_llm(config, streaming=False, thinking=False)
        llm_with_tools = llm.bind_tools([web_search])

        # 工具调用循环（最多迭代 3 次，避免无限循环）
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
                            yield StreamEvent(type="thinking", reasoning=reasoning)
                        if chunk.content:
                            yield chunk.content
                return

            reasoning = self._extract_reasoning(accumulated)
            if reasoning:
                yield StreamEvent(type="thinking", reasoning=reasoning)
            if accumulated.content:
                yield accumulated.content

            lc_messages.append(accumulated)

            for tool_call in tool_calls:
                tool_name = tool_call.get("name", "")
                tool_args = tool_call.get("args", {})
                tool_id = tool_call.get("id", "")

                tool_start_time = time.monotonic()
                yield StreamEvent(
                    type="tool_start",
                    name=tool_name,
                    args=tool_args,
                    tool_call_id=tool_id,
                )

                if tool_name == "web_search":
                    query = tool_args.get("query", "")
                    result = do_search(query)
                else:
                    result = f"未知工具: {tool_name}"

                yield StreamEvent(
                    type="tool_result",
                    name=tool_name,
                    result=result,
                    tool_call_id=tool_id,
                    elapsed_ms=int((time.monotonic() - tool_start_time) * 1000),
                )

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
                    yield StreamEvent(type="thinking", reasoning=reasoning)
                if chunk.content:
                    yield chunk.content


provider_registry.register("deepseek", DeepSeekProvider())
