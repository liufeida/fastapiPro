# AI 架构文档生成 - Product Requirement Document

## Overview
- **Summary**: 为 fastapi-demo 项目生成两份架构总结文档，分别记录 LangChain 的使用方式与多模型编排机制、以及 SSE 流式处理的完整链路（事件类型定义、遇到的问题与解决方案）。文档以 Markdown 格式输出到项目根目录下的独立文件夹 `docs/ai-architecture/`。
- **Purpose**: 让后续维护者或新成员快速理解项目中 AI 模块的设计思路、技术选型决策和踩过的坑，降低上手成本。
- **Target Users**: 项目开发者、维护者、Code Review 参与者。

## Goals
- 产出一份完整、准确的 LangChain 使用与多模型编排架构文档
- 产出一份完整、准确的 SSE 流式处理与事件类型定义文档
- 文档内容必须基于真实代码（已通读 `app/services/ai/` 全部文件与路由层）

## Non-Goals (Out of Scope)
- 不生成 API 接口文档（已有 OpenAPI/Swagger）
- 不修改现有业务代码
- 不引入新的依赖或重构

## Background & Context
项目已实现一套完整的 AI 模型统一接入平台，核心文件分布：
- **Provider 抽象层**: `app/services/ai/base.py`（AIProvider 抽象基类 + StreamEvent + EventType）
- **Provider 实现**: `app/services/ai/deepseek_provider.py`、`qwen_provider.py`、`ollama_provider.py`
- **注册中心**: `app/services/ai/registry.py`
- **调度器**: `app/services/ai/dispatcher.py`（身份系统提示词注入、能力校验、日志包装）
- **SSE 构造**: `app/services/ai/sse.py`（`build_sse` 函数）
- **路由层**: `app/api/v1/ai.py`（`_event_generator` 手动拼接完整 SSE 事件序列）
- **日志**: `app/services/ai_logger.py`（`wrap_stream_for_logging` 包装异步迭代器）

关键技术决策：
1. `thinking=true` 时必须走原生 httpx 直接消费 SSE，因为 LangChain 的 ChatOpenAI 会清除 DeepSeek 扩展的 `reasoning_content` 字段
2. SSE 不用 EventSourceResponse，而是手动构造 bytes 喂给 StreamingResponse，配合 `event:` 行实现自定义事件类型
3. httpx streaming 超时必须设 `read=None`，避免 thinking 阶段长时间无数据时连接被关闭
4. 工具调用循环最多迭代 3 次，耗尽后强制让模型输出最终回答，确保 SSE 流有完整 Done 事件

## Functional Requirements

### FR-1: LangChain 使用方式与多模型编排文档
文档须覆盖以下内容：
- LangChain 在项目中扮演的角色（ChatDeepSeek、ChatOpenAI、bind_tools、astream/ainvoke）
- 消息模型的双向转换（dict ↔ LangChain BaseMessage）
- 三层架构：Provider 抽象基类 → Provider 实现 → 调度器
- 多模型编排机制：ProviderRegistry 注册 + AIModelConfig 数据库配置 + AIDispatcher 统一调度
- 身份系统提示词注入（`_build_identity_system`）
- 能力校验（supports_thinking / supports_tools）
- thinking 模式下的双通道设计（LangChain 路径 vs 原生 httpx 路径）
- 工具调用循环实现（bind_tools + 3 次迭代上限）
- 日志包装机制（wrap_stream_for_logging）

### FR-2: SSE 流式处理文档
文档须覆盖以下内容：
- 整体链路：Provider yield StreamChunk → Dispatcher 透传 → 路由层 `_event_generator` 组装完整事件序列 → `build_sse` 构造 bytes → StreamingResponse 输出
- EventType 枚举定义与每个事件的 JSON 字段
- 完整事件序列（start → thinking_start → thinking* → thinking_end → content_start → content* → content_end → tool_start → tool_result → usage → end → Done）
- SSE 格式细节（event 行、data 行、\n\n 分隔、纯 bytes）
- 遇到的问题与解决方案：
  1. LangChain 清除 reasoning_content → 原生 httpx 直接消费 SSE
  2. EventSourceResponse keepalive task 导致 BrokenResourceError → 手动构造 bytes
  3. httpx read timeout 导致 thinking 阶段断开 → read=None
  4. 工具循环耗尽后无输出 → 强制最终回答
  5. 中间件截断流导致 Done 事件缺失 → 完整收集后统一 yield
- 前端如何消费（event 类型监听）

### FR-3: 文档存放位置
- 创建 `docs/ai-architecture/` 目录
- 文件命名清晰：`01-langchain-and-orchestration.md`、`02-sse-streaming.md`

## Non-Functional Requirements
- **准确性**: 所有代码引用、技术细节、文件路径必须与当前仓库一致
- **可读性**: 使用合适的标题层级、代码块、表格
- **时效性**: 不臆测未来设计，只描述当前已实现内容

## Constraints
- **Technical**: Markdown 格式，UTF-8 编码
- **Dependencies**: 无外部依赖
- **Business**: 仅文档生成，不修改业务代码

## Assumptions
- 阅读者具备 Python/FastAPI/LangChain 基础
- 代码即权威来源（不依赖口头描述）

## Acceptance Criteria

### AC-1: LangChain 文档覆盖完整
- **Given**: 项目中 LangChain 的所有使用点
- **When**: 阅读文档
- **Then**: 能解释 LangChain 在项目中的角色、两种使用路径、bind_tools 用法、BaseMessage 转换
- **Verification**: `human-judgment`

### AC-2: 多模型编排架构清晰
- **Given**: Provider 抽象 → Registry → Dispatcher → 路由 这四层
- **When**: 阅读文档
- **Then**: 能画出调用链时序图、说明新增一个模型需要哪些步骤
- **Verification**: `human-judgment`

### AC-3: SSE 事件类型完整列出
- **Given**: EventType 枚举所有值
- **When**: 阅读文档
- **Then**: 每个事件的 type、JSON 字段、含义、触发时机都能查到
- **Verification**: `human-judgment`

### AC-4: SSE 问题与解决方案完整
- **Given**: 项目 memory 中记录的 5 个 SSE 相关坑 + 代码注释中的说明
- **When**: 阅读文档
- **Then**: 每个问题的症状、根因、解决手段都有记录
- **Verification**: `human-judgment`

### AC-5: 文件位置正确
- **Given**: 项目根目录
- **When**: 查看 `docs/ai-architecture/`
- **Then**: 两份 md 文件存在且命名符合约定
- **Verification**: `programmatic`

## Open Questions
- 无（代码已全部读完，信息充分）
