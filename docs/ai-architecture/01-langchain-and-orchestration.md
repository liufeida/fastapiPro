# LangChain 使用方式与多模型编排架构

> 本文档总结 fastapi-demo 项目中 AI 对话能力的整体架构，覆盖 LangChain 集成、Provider 注册机制、AIDispatcher 调度流程、thinking 双通道、工具调用循环与日志包装。

---

## 1. 架构总览

### 1.1 四层调用链

```mermaid
flowchart LR
    A["路由层 API<br/>(FastAPI Router)"] -->|chat / chat_stream_with_tools| B["AIDispatcher<br/>dispatcher.py"]
    B -->|provider_registry.get(code)| C["ProviderRegistry<br/>registry.py"]
    C --> D1["DeepSeekProvider<br/>deepseek_provider.py"]
    C --> D2["QwenProvider<br/>qwen_provider.py"]
    C --> D3["OllamaProvider<br/>ollama_provider.py"]
```

| 层级 | 模块 | 职责 |
|------|------|------|
| 路由层 | FastAPI Router | 解析参数、鉴权、构造 SSE 响应 |
| 调度层 | `AIDispatcher` | 查库拿配置 → 能力校验 → 注入身份 system prompt → 调用 Provider |
| 注册层 | `ProviderRegistry` | 按 `provider_code` 存放 Provider 实例，启动时由 `__init__.py` 导入触发注册副作用 |
| 实现层 | `AIProvider` 子类 | 封装具体模型 SDK / HTTP，输出统一 `StreamChunk`（`str | StreamEvent`） |

### 1.2 依赖一览

`pyproject.toml`（节选）：

```toml
dependencies = [
    "httpx>=0.28.1",
    "langchain-deepseek>=1.1.0",
    "langchain-openai>=1.4.1",
    # ... 其他
]
```

| 包 | 用途 | 消费方 |
|----|------|--------|
| `langchain-deepseek` | 提供 `ChatDeepSeek` 类 | `DeepSeekProvider` |
| `langchain-openai` | 提供 `ChatOpenAI` 类（DashScope OpenAI 兼容端点） | `QwenProvider` |
| `langchain-core` | `SystemMessage` / `HumanMessage` / `AIMessage` / `ToolMessage` / `bind_tools` / `astream` / `ainvoke` | 两个 LangChain 路径 Provider |
| `httpx` | 原生 SSE 流消费 + Ollama HTTP | `DeepSeekProvider._stream_raw` / `QwenProvider._stream_raw` / `OllamaProvider` |

---

## 2. LangChain 在项目中的角色

项目**不是**纯 LangChain 应用。LangChain 只承担两件事：

1. **ChatDeepSeek**（`langchain-deepseek`）用于 DeepSeek 模型的非 thinking 路径
2. **ChatOpenAI**（`langchain-openai`）用于 Qwen 模型，指向 DashScope OpenAI 兼容端点

两个 Provider 的 `_get_llm` 工厂方法分别返回对应类：

```python
# deepseek_provider.py:107
def _get_llm(self, config, streaming=False, thinking=False) -> ChatDeepSeek:
    extra_body = (
        {"thinking": {"type": "enabled"}} if thinking
        else {"thinking": {"type": "disabled"}}
    )
    return ChatDeepSeek(
        model=config.model_code,
        api_key=config.api_key,
        base_url=config.base_url or "https://api.deepseek.com",
        temperature=config.temperature if config.temperature is not None else 0.7,
        streaming=streaming,
        extra_body=extra_body,
    )
```

```python
# qwen_provider.py:101
def _get_llm(self, config, streaming=False, thinking=False) -> ChatOpenAI:
    extra_body = {"enable_thinking": True} if thinking else {"enable_thinking": False}
    return ChatOpenAI(
        model=config.model_code,
        api_key=config.api_key,
        base_url=config.base_url
        or "https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature=config.temperature if config.temperature is not None else 0.7,
        streaming=streaming,
        extra_body=extra_body,
    )
```

### 不用 LangChain 的场景

| Provider | 情况 | 替代方案 |
|----------|------|----------|
| DeepSeek | `thinking=True` | 原生 `httpx` → `_stream_raw` |
| Qwen | `thinking=True` | 原生 `httpx` → `_stream_raw` |
| Ollama | 全部 | 纯原生 `httpx.AsyncClient`，不依赖 LangChain |

**核心分裂原因：LangChain 在流式消费 SSE 时会清除 `reasoning_content` 字段**。思考类模型（deepseek-reasoner、qwen-max 等）必须拿到该字段才能在前端渲染"思考中…"动画，因此 `thinking=True` 一律走原生路径。

---

## 3. 消息模型双向转换

LangChain 与原生 HTTP 两边都需要"消息列表"，但格式不同。两个 Provider 各实现了一对对称方法。

### 3.1 `_to_langchain_messages`：dict → BaseMessage

```python
# deepseek_provider.py:50
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
```

| dict role | 映射为 LangChain |
|-----------|------------------|
| `system`  | `SystemMessage` |
| `user`    | `HumanMessage` |

### 3.2 `_to_dict_messages`：BaseMessage → dict（含 tool_calls / ToolMessage）

```python
# deepseek_provider.py:62
def _to_dict_messages(self, langchain_messages) -> list[dict]:
    # AIMessage.tool_calls → 标准 OpenAI tool_calls 格式
    # ToolMessage → {"role": "tool", "tool_call_id": ..., "content": ...}
```

| LangChain 类型 | 产出 dict 结构 |
|----------------|----------------|
| `SystemMessage` | `{"role": "system", "content": ...}` |
| `HumanMessage`  | `{"role": "user", "content": ...}` |
| `AIMessage`（有 `tool_calls`） | `{"role": "assistant", "content": ..., "tool_calls": [{"id","type":"function","function":{"name","arguments":...}}]}` |
| `ToolMessage`   | `{"role": "tool", "tool_call_id": ..., "content": ...}` |

### 3.3 为什么需要双向转换

工具循环中两条路径共存：

- **LangChain 路径**（`enable_search=True`）：`bind_tools` → `ainvoke` 拿到 `AIMessage` → 执行 tool → 追加 `ToolMessage` → 再调用
- **原生路径**（`thinking=True` 且工具循环结束后输出最终回答）：LangChain 消息链要转成 dict 送进 `_stream_raw`，以便拿到 `reasoning_content`

因此在工具循环耗尽时，代码会显式转换：

```python
# deepseek_provider.py:296
dict_messages = self._to_dict_messages(lc_messages)
async for chunk in self._stream_raw(config, dict_messages, thinking=True):
    yield chunk
```

---

## 4. AIProvider 抽象基类

`app/services/ai/base.py` 定义了所有 Provider 必须实现的三个抽象方法：

```python
class AIProvider(ABC):
    @abstractmethod
    async def chat(self, config, prompt: str, system: Optional[str] = None, thinking: bool = False) -> str:
        """非流式对话，返回完整回复。"""
        ...

    @abstractmethod
    async def chat_stream(self, config, prompt: str, system: Optional[str] = None, thinking: bool = False) -> AsyncIterator[StreamChunk]:
        """流式对话，逐块返回内容。"""
        ...

    @abstractmethod
    async def chat_stream_with_tools(self, config, prompt: str, system: Optional[str] = None, thinking: bool = False, enable_search: bool = False, file_context: Optional[str] = None) -> AsyncIterator[StreamChunk]:
        """增强版流式对话：支持文件上下文与联网搜索工具调用循环。"""
        ...
```

### 统一的流式输出模型

基类同时定义了 SSE 事件协议：

```python
class EventType(str, Enum):
    START = "start"
    THINKING_START = "thinking_start"
    THINKING = "thinking"
    THINKING_END = "thinking_end"
    CONTENT_START = "content_start"
    CONTENT = "content"
    CONTENT_END = "content_end"
    TOOL_START = "tool_start"
    TOOL_RESULT = "tool_result"
    USAGE = "usage"
    END = "end"
    ERROR = "error"
    TOOL = "tool"
    DONE = "Done"

@dataclass
class StreamEvent:
    type: str
    request_id: Optional[str] = None
    timestamp: Optional[str] = None
    # ... 完整字段见 base.py:27

StreamChunk = Union[str, StreamEvent]
```

### 为什么禁止路由层裸调第三方 HTTP

基类文档明确写道：**"禁止在路由层直接裸调第三方 HTTP"**。约束来自三层：

1. 配置统一走 `AIModelConfig`（DB 表），路由层永远不碰 `api_key`、`base_url`
2. 能力校验统一在 `AIDispatcher.check_capability` 完成（thinking / tools 开关）
3. 日志、trace、异常包装统一在 Dispatcher 与 `wrap_stream_for_logging` 中处理

---

## 5. ProviderRegistry 注册机制

`app/services/ai/registry.py` 实现了一个简单的单例注册表：

```python
class ProviderRegistry:
    def __init__(self):
        self._providers: Dict[str, AIProvider] = {}

    def register(self, provider_code: str, provider: AIProvider) -> None: ...
    def get(self, provider_code: str) -> AIProvider: ...
    def list_providers(self) -> list[str]: ...

provider_registry = ProviderRegistry()
```

### 注册触发时机：`__init__.py` 导入副作用

```python
# app/services/ai/__init__.py
from app.services.ai import deepseek_provider  # noqa: F401
from app.services.ai import ollama_provider     # noqa: F401
from app.services.ai import qwen_provider       # noqa: F401
```

每个 Provider 模块**文件末尾**执行一次注册：

```python
# deepseek_provider.py:364
provider_registry.register("deepseek", DeepSeekProvider())

# qwen_provider.py:339
provider_registry.register("qwen", QwenProvider())

# ollama_provider.py:111
provider_registry.register("ollama", OllamaProvider())
```

只要应用启动时（任何地方）`from app.services.ai import ai_dispatcher`，三个 Provider 就会被自动注册到 `provider_registry`，无需额外的初始化函数。

### DB 与注册的对应关系

`AIModelConfig.provider_code` 字符串必须与注册名精确匹配：

| 注册名 | DB `provider_code` 取值 | 实现类 |
|--------|-------------------------|--------|
| `deepseek` | `deepseek` | `DeepSeekProvider` |
| `qwen` | `qwen` | `QwenProvider` |
| `ollama` | `ollama` | `OllamaProvider` |

---

## 6. AIDispatcher 调度流程

`app/services/ai/dispatcher.py` 是路由层与 Provider 之间的唯一调度入口。

### 6.1 resolve：model_code → AIModelConfig

```python
async def resolve(self, session: AsyncSession, model_code: str) -> AIModelConfig:
    config = await ai_model_config_repository.get_by_model_code(session, model_code)
    if not config or not config.is_enabled:
        raise BusinessException(code=404, message="模型不可用或未配置")
    return config
```

同时校验了**软删除**（`is_deleted=True` 已被仓储层过滤）和**启用状态**（`is_enabled=False` 直接 404）。

### 6.2 check_capability：能力校验

```python
def check_capability(self, config, thinking: bool, enable_search: bool) -> None:
    if thinking and not config.supports_thinking:
        raise BusinessException(code=400, message="该模型不支持思考模式")
    if enable_search and not config.supports_tools:
        raise BusinessException(code=400, message="该模型不支持工具调用")
```

这样 Ollama（`supports_thinking=False`、`supports_tools=False`）在 Dispatcher 层就会被拦截，不会走到 Provider 的 `chat_stream_with_tools`。

### 6.3 `_build_identity_system`：身份 system prompt 注入

```python
def _build_identity_system(config: AIModelConfig, user_system: Optional[str]) -> str:
    now = datetime.now(timezone.utc).astimezone()
    identity = (
        f"你是 {config.model_name}（model_code: {config.model_code}）。\n"
        f"当前日期时间: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}（{now.strftime('%A')}）。"
    )
    db_prompt = prompt_cache.resolve(config.model_code)
    db_content = db_prompt.content if db_prompt else ""
    parts = [identity]
    if db_content:
        parts.append(db_content)
    if user_system:
        parts.append(user_system)
    return "\n".join(parts)
```

拼接顺序：

1. **身份声明**：`model_name` + `model_code`
2. **当前日期时间**：让模型能回答"今天几号"、"星期几"（时区 `astimezone()`）
3. **DB 配置的系统提示词**：从 `prompt_cache` 取（按 `model_code` 精确匹配 → 全局默认）
4. **用户自定义 system**：最后追加

### 6.4 chat / chat_stream_with_tools 主流程

```python
async def chat_stream_with_tools(self, session, model_code, prompt, system, thinking, enable_search, file_context, _config=None):
    config = _config if _config is not None else await self.resolve(session, model_code)
    self.check_capability(config, thinking, enable_search)
    provider = provider_registry.get(config.provider_code)
    system = _build_identity_system(config, system)

    ai_logger = AIChatLogger()
    ai_logger.start(config, prompt, system)

    try:
        chunk_iter = provider.chat_stream_with_tools(config, prompt, system, thinking, enable_search, file_context)
        async for chunk in wrap_stream_for_logging(chunk_iter, ai_logger):
            yield chunk
    except Exception as exc:
        ai_logger.record_error(f"{type(exc).__name__}: {str(exc)}")
        ai_logger.enqueue()
        raise
```

路由层可通过 `_config` 参数把预查询结果透传进来，避免重复查库。

---

## 7. thinking 双通道设计

两个 Provider 的 `chat_stream` 方法都按 `thinking` 做了路径分叉：

| 场景 | 路径 | 流式接口 |
|------|------|----------|
| `thinking=False` | LangChain | `llm.astream(lc_messages)` → 从 `chunk.additional_kwargs["reasoning_content"]` 可能还能拿到部分思考 |
| `thinking=True` | 原生 httpx | `_stream_raw(config, messages, thinking=True)` → 消费 SSE `reasoning_content` 字段 |

`OllamaProvider` 不实现 thinking，由 Dispatcher 能力校验层提前拦截。

### 分裂原因

LangChain 在解析 SSE 时会把 `reasoning_content` 字段**剥离掉**，上游 `AIMessageChunk` 的 `content` 里只保留最终回答。思考类模型（deepseek-reasoner、deepseek-v4-pro 等）前端需要渲染"思考中…"阶段，因此必须绕过 LangChain 自己消费原始 SSE。

### `_stream_raw` 实现要点

```python
# deepseek_provider.py:127
async def _stream_raw(self, config, messages, thinking=False) -> AsyncIterator[StreamChunk]:
    # 使用 read=None 超时——thinking 模式下 reasoning → content 之间可能长时间间隔
    async with httpx.AsyncClient(timeout=_HTTPX_STREAM_TIMEOUT) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as response:
            async for line in response.aiter_lines():
                # data: [DONE] 结束
                # delta.reasoning_content → StreamEvent(type="thinking", reasoning=...)
                # delta.content → 直接 yield str
    # 最后一个 chunk 的 usage → StreamEvent(type="usage", ...)
```

超时配置 `read=None` 是关键——thinking 阶段模型可能长时间不吐字，普通 `read_timeout` 会把连接掐掉。

---

## 8. 工具调用循环实现

工具调用只在 `enable_search=True` 时触发。Provider 统一使用 LangChain 的 `bind_tools` + 原生循环。

### 8.1 绑定工具

```python
# deepseek_provider.py:285-287
lc_messages = self._to_langchain_messages(messages)
llm = self._get_llm(config, streaming=False, thinking=False)
llm_with_tools = llm.bind_tools([web_search])
```

`web_search` 是 LangChain 格式的工具定义（Pydantic `BaseModel` + docstring），位于 `app/services/web_search.py`。

### 8.2 循环最多 3 次

```python
# deepseek_provider.py:290
for _ in range(3):
    accumulated: AIMessage = await llm_with_tools.ainvoke(lc_messages)
    tool_calls = accumulated.tool_calls

    if not tool_calls:
        # 最终回答 → 流式输出（走 thinking=True 原生 / thinking=False LangChain）
        return

    # 有工具调用 → yield tool_start → do_search → 追加 ToolMessage → 下一轮
    for tool_call in tool_calls:
        yield StreamEvent(type="tool_start", ...)
        if tool_name == "web_search":
            result = do_search(query)
        yield StreamEvent(type="tool_result", ...)
        lc_messages.append(ToolMessage(content=result, tool_call_id=tool_id))
```

### 8.3 循环耗尽后的兜底

```python
# deepseek_provider.py:349
logger.warning("工具调用循环耗尽，强制让模型输出最终回答")
if thinking:
    dict_messages = self._to_dict_messages(lc_messages)
    async for chunk in self._stream_raw(config, dict_messages, thinking=True):
        yield chunk
else:
    async for chunk in llm_with_tools.astream(lc_messages):
        ...
```

强制再让模型对已有消息链回答一次，避免 SSE 流中途沉默。

---

## 9. 日志包装机制

### 9.1 `wrap_stream_for_logging`：包装 AsyncIterator

`app/services/ai_logger.py` 在 **不改变流语义** 的前提下透传 chunk：

```python
async def wrap_stream_for_logging(chunk_iter: AsyncIterator, logger: AIChatLogger) -> AsyncIterator:
    try:
        async for chunk in chunk_iter:
            if isinstance(chunk, str):
                logger.record_content(chunk)
            elif isinstance(chunk, StreamEvent):
                if chunk.type == "thinking":
                    logger.record_thinking(chunk.reasoning or chunk.result or "")
            yield chunk          # 透传，不缓存等结束
    except Exception as exc:
        logger.record_error(...)
        raise
    finally:
        logger.enqueue()
```

- **yield 透传**：chunk 一到立刻向下游推送，不攒到结束，保证 SSE 首包延迟不受影响
- **幂等 `enqueue`**：内部用 `_enqueued` 标志防重复入队（Dispatcher 层 `finally` 也会调一次）

### 9.2 `AIChatLogger` 状态机

| 方法 | 时机 | 做什么 |
|------|------|--------|
| `start(config, prompt, system)` | Dispatcher 开始调度 | 记录用户 prompt / system prompt / model_code / provider_code / `_start_time` |
| `record_content(chunk)` | 每次 yield str 时 | 追加到 `_collected` |
| `record_thinking(content)` | 每次 yield thinking StreamEvent 时 | 追加到 `_thinking_parts`，首次记录 `_thinking_start_time` |
| `record_error(msg)` | 异常时 | 设置 `_error=True` + `_error_msg` |
| `enqueue()` | finally | 计算 `duration_ms` / `thinking_ms`，整条 JSON 入队 `log_queue.enqueue(LOG_TYPE_AI, {...})` |

---

## 10. 新增一个模型 Provider 的步骤

以新增 `anthropic` 为例：

### Step 1：创建 Provider 类，继承 `AIProvider`

```python
# app/services/ai/anthropic_provider.py
from app.services.ai.base import AIProvider, StreamChunk, StreamEvent
from app.services.ai.registry import provider_registry

class AnthropicProvider(AIProvider):
    async def chat(self, config, prompt, system=None, thinking=False):
        ...

    async def chat_stream(self, config, prompt, system=None, thinking=False):
        ...

    async def chat_stream_with_tools(self, config, prompt, system=None, thinking=False, enable_search=False, file_context=None):
        ...
```

### Step 2：实现三个抽象方法

- **`chat`**：非流式完整回复
- **`chat_stream`**：流式，边收边 `yield`，内容用 `str`，思考用 `StreamEvent(type="thinking", ...)`
- **`chat_stream_with_tools`**：至少要在 `enable_search=False` 时退化为 `chat_stream`；如果要支持工具循环，参考 `DeepSeekProvider` 的 `bind_tools + for _ in range(3)` 模板

### Step 3：模块末尾注册

```python
# app/services/ai/anthropic_provider.py 末尾
provider_registry.register("anthropic", AnthropicProvider())
```

### Step 4：在 `__init__.py` 中 import 触发注册

```python
# app/services/ai/__init__.py
from app.services.ai import anthropic_provider  # noqa: F401
```

### Step 5：在 `ai_model_config` 表插入配置

`provider_code` 列必须与注册名精确对应：

| 字段 | 示例值 |
|------|--------|
| `provider_code` | `anthropic` |
| `model_code` | `claude-sonnet-4-20250514` |
| `model_name` | `Claude Sonnet 4` |
| `api_key` | `sk-ant-xxxx` |
| `base_url` | `https://api.anthropic.com`（默认可留空） |
| `supports_thinking` | `true` / `false` |
| `supports_tools` | `true` / `false` |
| `supports_stream` | `true` |
| `is_enabled` | `true` |

### 完整 Checklist

| # | 位置 | 做什么 |
|---|------|--------|
| 1 | `app/services/ai/<xxx>_provider.py` | 新建文件，类继承 `AIProvider` |
| 2 | 同上 | 实现 `chat` / `chat_stream` / `chat_stream_with_tools` |
| 3 | 同上末尾 | `provider_registry.register("<code>", XxxProvider())` |
| 4 | `app/services/ai/__init__.py` | `from app.services.ai import xxx_provider  # noqa: F401` |
| 5 | DB `ai_model_config` | INSERT 一条，`provider_code` 匹配注册名 |

---

## 文件索引

| 文件 | 关键符号 |
|------|----------|
| `app/services/ai/base.py` | `AIProvider`（ABC）、`StreamEvent`、`EventType`、`StreamChunk` |
| `app/services/ai/registry.py` | `ProviderRegistry`、`provider_registry`（单例） |
| `app/services/ai/dispatcher.py` | `AIDispatcher`、`ai_dispatcher`（单例）、`_build_identity_system` |
| `app/services/ai/deepseek_provider.py` | `DeepSeekProvider`、`_get_llm`、`_stream_raw`、`_to_langchain_messages`、`_to_dict_messages` |
| `app/services/ai/qwen_provider.py` | `QwenProvider`（同上方法名） |
| `app/services/ai/ollama_provider.py` | `OllamaProvider`、`_resolve_endpoint` |
| `app/services/ai/__init__.py` | 导入触发注册、重导出 |
| `app/services/ai_logger.py` | `AIChatLogger`、`wrap_stream_for_logging` |
| `app/models/ai_model_config.py` | `AIModelConfig`（SQLModel 表）、`AIModelConfigBase` |
