import logging
import os
from dataclasses import dataclass
from typing import AsyncIterator, Optional, Union

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_deepseek import ChatDeepSeek

from app.core.exceptions import BusinessException
from app.services.web_search import do_search, web_search

logger = logging.getLogger(__name__)

# DeepSeek 配置（从环境变量读取，见项目根目录 .env 文件）
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
# 新模型名（旧的 deepseek-chat / deepseek-reasoner 已于 2026/07/24 停用）
# deepseek-v4-flash：速度快、成本低；deepseek-v4-pro：推理能力更强
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")


@dataclass
class ToolEvent:
    """工具调用相关事件，供路由层区分 SSE 事件类型。

    type="tool": 模型决定调用工具，args 为工具入参
    type="tool_result": 后端执行工具完毕，result 为执行结果
    type="thinking": 模型的思考过程内容（reasoning_content）
    """

    type: str  # "tool" | "tool_result" | "thinking"
    name: str
    args: Optional[dict] = None
    result: Optional[str] = None


# 流式生成器产出类型：内容块(str) 或 工具事件(ToolEvent)
StreamChunk = Union[str, ToolEvent]


class DeepSeekService:
    """基于 langchain-deepseek 的 DeepSeek 调用服务。

    使用 LangChain 官方的 ChatDeepSeek 集成包，自动解析 DeepSeek 扩展的
    reasoning_content 字段（存放在 chunk.additional_kwargs["reasoning_content"]）。
    """

    def _get_llm(
        self,
        model: str = DEEPSEEK_MODEL,
        temperature: float = 0.7,
        streaming: bool = False,
        thinking: bool = False,
    ) -> ChatDeepSeek:
        """创建 ChatDeepSeek 实例。

        - thinking=False（默认）：关闭思考模式，响应更快，支持 temperature
        - thinking=True：开启思考模式，适合复杂推理（temperature 等参数无效）
        """
        if not DEEPSEEK_API_KEY:
            raise BusinessException(code=500, message="DeepSeek API Key 未配置")

        # DeepSeek 通过 extra_body 控制思考模式开关
        # thinking=True 时开启思考模式，API 期望 ThinkingOptions 结构体
        extra_body = {"thinking": {"type": "enabled"}} if thinking else {}

        logger.info(
            f"DeepSeek LLM 初始化: model={model}, thinking={thinking}, extra_body={extra_body}"
        )

        return ChatDeepSeek(
            model=model,
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            temperature=temperature,
            streaming=streaming,
            extra_body=extra_body,
        )

    @staticmethod
    def _extract_reasoning(chunk: AIMessage) -> Optional[str]:
        """从 AIMessageChunk 中提取 reasoning_content（ChatDeepSeek 会放入 additional_kwargs）。"""
        return chunk.additional_kwargs.get("reasoning_content")

    def _build_messages(
        self,
        prompt: str,
        system: Optional[str] = None,
        file_context: Optional[str] = None,
    ) -> list[BaseMessage]:
        """组装 LangChain 消息列表。"""
        final_prompt = prompt
        if file_context:
            final_prompt = f"【文件上下文】\n{file_context}\n\n【用户问题】\n{prompt}"
        messages: list[BaseMessage] = []
        if system:
            messages.append(SystemMessage(content=system))
        messages.append(HumanMessage(content=final_prompt))
        return messages

    async def _astream_with_reasoning(
        self,
        llm: ChatDeepSeek,
        messages: list[BaseMessage],
    ) -> AsyncIterator[StreamChunk]:
        """统一的流式输出：先输出思考内容（如有），再输出回答内容。

        ChatDeepSeek 会把 reasoning_content 放入 chunk.additional_kwargs，
        这里统一提取，避免每个调用处重复代码。
        """
        async for chunk in llm.astream(messages):
            reasoning = self._extract_reasoning(chunk)
            if reasoning:
                yield ToolEvent(type="thinking", name="reasoning", result=reasoning)
            if chunk.content:
                yield chunk.content

    def chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        thinking: bool = False,
    ) -> str:
        """非流式对话，返回完整回复。"""
        llm = self._get_llm(streaming=False, thinking=thinking)
        messages = self._build_messages(prompt, system)
        response = llm.invoke(messages)
        return response.content

    async def chat_stream(
        self,
        prompt: str,
        system: Optional[str] = None,
        thinking: bool = False,
    ) -> AsyncIterator[StreamChunk]:
        """流式对话，逐块返回内容。开启 thinking 时会先输出思考内容。"""
        llm = self._get_llm(streaming=True, thinking=thinking)
        messages = self._build_messages(prompt, system)
        async for chunk in self._astream_with_reasoning(llm, messages):
            yield chunk

    async def chat_stream_with_tools(
        self,
        prompt: str,
        system: Optional[str] = None,
        thinking: bool = False,
        enable_search: bool = False,
        file_context: Optional[str] = None,
    ) -> AsyncIterator[StreamChunk]:
        """增强版流式对话：支持文件上下文与联网搜索工具调用循环。

        - file_context 非空时，拼接到 prompt 前作为上下文
        - enable_search=True 时，通过 bind_tools 注册 web_search 工具，
          模型可在需要时调用，后端执行后把结果回传，继续生成最终回答
        - enable_search=False 时，退化为纯流式（不绑定工具），行为与 chat_stream 一致
        """
        messages = self._build_messages(prompt, system, file_context)

        # 关闭搜索：直接走纯流式
        if not enable_search:
            llm = self._get_llm(streaming=True, thinking=thinking)
            async for chunk in self._astream_with_reasoning(llm, messages):
                yield chunk
            return

        # 开启搜索：绑定 web_search 工具
        llm = self._get_llm(streaming=True, thinking=thinking)
        llm_with_tools = llm.bind_tools([web_search])

        # 工具调用循环（最多迭代 5 次，避免无限循环）
        for _ in range(5):
            accumulated: AIMessage = await llm_with_tools.ainvoke(messages)
            tool_calls = accumulated.tool_calls

            # 没有工具调用：流式输出最终回答（含思考内容）
            if not tool_calls:
                async for chunk in self._astream_with_reasoning(llm_with_tools, messages):
                    yield chunk
                return

            # 有工具调用：先输出模型在 tool_call 前可能产生的思考/内容（如有）
            reasoning = self._extract_reasoning(accumulated)
            if reasoning:
                yield ToolEvent(type="thinking", name="reasoning", result=reasoning)
            if accumulated.content:
                yield accumulated.content

            # 把模型决策（含 tool_calls）加入上下文
            messages.append(accumulated)

            # 逐个执行工具
            for tool_call in tool_calls:
                tool_name = tool_call.get("name", "")
                tool_args = tool_call.get("args", {})
                tool_id = tool_call.get("id", "")

                # 推送工具调用事件
                yield ToolEvent(type="tool", name=tool_name, args=tool_args)

                # 执行 web_search
                if tool_name == "web_search":
                    query = tool_args.get("query", "")
                    result = do_search(query)
                else:
                    result = f"未知工具: {tool_name}"

                # 推送工具结果事件
                yield ToolEvent(
                    type="tool_result", name=tool_name, result=result
                )

                # 把工具结果作为 ToolMessage 回传给模型
                messages.append(
                    ToolMessage(content=result, tool_call_id=tool_id)
                )

            # 进入下一轮：让模型基于工具结果继续生成（可能再次调用工具或输出最终回答）


deepseek_service = DeepSeekService()
