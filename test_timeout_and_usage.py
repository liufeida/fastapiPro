"""
测试 per-chunk 超时机制 + AI 日志 usage 收集 + 能力校验失败也写日志

运行：.venv\\Scripts\\python.exe test_timeout_and_usage.py
"""
from __future__ import annotations

import asyncio
import sys
import time
from typing import Any

sys.path.insert(0, ".")

results: list[dict[str, Any]] = []


def record(name: str, passed: bool, detail: str = "") -> None:
    results.append({"name": name, "passed": passed, "detail": detail})
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}")
    if detail:
        for line in detail.strip().splitlines():
            print(f"         {line}")


# ─── 复用被测函数 ────────────────────────────────────────────

from app.api.v1.ai import _iter_with_chunk_timeout


async def _slow_generator(delay_per_chunk: float, chunks: list[str]):
    """模拟一个 async generator，产出 chunks 但每个 chunk 之间有延迟。"""
    for c in chunks:
        await asyncio.sleep(delay_per_chunk)
        yield c


async def _stuck_generator():
    """模拟永远卡住的 async generator（第一个 chunk 永远不来）。"""
    await asyncio.sleep(999)
    yield "this should never arrive"


# ─── 测试 1: 正常迭代不会触发超时 ────────────────────────────

async def test_normal_iteration_ok():
    chunks = ["hello", " ", "world"]
    start = time.perf_counter()
    collected = []
    async for item in _iter_with_chunk_timeout(
        _slow_generator(0.01, chunks), per_chunk_timeout=1.0
    ):
        collected.append(item)
    elapsed = time.perf_counter() - start
    ok = collected == chunks and elapsed < 1.0
    record(
        "正常迭代不受超时影响",
        ok,
        f"collected={collected}, elapsed={elapsed:.3f}s (<1s)",
    )
    return ok


# ─── 测试 2: 迭代间隔超过阈值 → TimeoutError ─────────────────

async def test_timeout_triggers_on_slow_chunk():
    start = time.perf_counter()
    try:
        async for item in _iter_with_chunk_timeout(
            _slow_generator(0.5, ["a", "b", "c"]), per_chunk_timeout=0.2
        ):
            pass
        record("chunk 间隔超时 → TimeoutError", False, "未触发 TimeoutError")
        return False
    except asyncio.TimeoutError:
        elapsed = time.perf_counter() - start
        ok = 0.2 < elapsed < 1.5
        record(
            "chunk 间隔超时 → TimeoutError",
            ok,
            f"elapsed={elapsed:.3f}s (预期 ~0.2s)",
        )
        return ok


# ─── 测试 3: 第一个 chunk 永远不来 → TimeoutError ────────────

async def test_timeout_on_first_chunk_stuck():
    start = time.perf_counter()
    try:
        async for item in _iter_with_chunk_timeout(
            _stuck_generator(), per_chunk_timeout=0.3
        ):
            pass
        record("第一个 chunk 卡死 → TimeoutError", False, "未触发 TimeoutError")
        return False
    except asyncio.TimeoutError:
        elapsed = time.perf_counter() - start
        ok = 0.3 < elapsed < 2.0
        record(
            "第一个 chunk 卡死 → TimeoutError",
            ok,
            f"elapsed={elapsed:.3f}s (预期 ~0.3s)",
        )
        return ok


# ─── 测试 4: AIChatLogger 正确收集 usage ────────────────────

async def test_ai_logger_records_usage():
    from app.services.ai_logger import AIChatLogger, wrap_stream_for_logging
    from app.services.ai.base import StreamEvent

    logger = AIChatLogger()
    logger.start(_FakeConfig(), "你好", "你是测试助手")

    collected_items: list[Any] = []

    async def fake_provider():
        yield "你好，"
        yield "世界！"
        yield StreamEvent(type="usage", prompt_tokens=15, completion_tokens=8)

    async for chunk in wrap_stream_for_logging(fake_provider(), logger):
        collected_items.append(chunk)

    # 不调 enqueue，直接看内部字段
    ok = logger._input_tokens == 15 and logger._output_tokens == 8
    record(
        "AIChatLogger 收集 StreamEvent(usage)",
        ok,
        f"input_tokens={logger._input_tokens}, output_tokens={logger._output_tokens}",
    )
    return ok


async def test_ai_logger_enqueue_writes_usage():
    """调用 enqueue 后，入队数据里应该带上真实 token 数。"""
    from app.services.ai_logger import AIChatLogger
    from app.services.log_queue import log_queue, LOG_TYPE_AI

    # 清空队列（简单处理：新建 logger）
    logger = AIChatLogger()
    logger.start(_FakeConfig(), "你好", "你是测试助手")
    logger.record_content("hi")
    logger.record_usage(prompt_tokens=42, completion_tokens=17)

    # 拦截 enqueue 写入的数据
    captured: list[dict] = []
    original_enqueue = log_queue.enqueue

    def spy_enqueue(log_type: str, data: dict):
        captured.append({"log_type": log_type, "data": data})

    log_queue.enqueue = spy_enqueue
    try:
        logger.enqueue()
    finally:
        log_queue.enqueue = original_enqueue

    if not captured:
        record("enqueue 入队带 usage", False, "enqueue 没有被调用")
        return False

    data = captured[0]["data"]
    ok = data.get("input_tokens") == 42 and data.get("output_tokens") == 17
    record(
        "enqueue 入队带 usage",
        ok,
        f"input_tokens={data.get('input_tokens')}, "
        f"output_tokens={data.get('output_tokens')}",
    )
    return ok


async def test_logger_start_accepts_model_code_string():
    """start() 可以直接传 model_code 字符串（不需要先有 config）。"""
    from app.services.ai_logger import AIChatLogger

    logger = AIChatLogger()
    logger.start("deepseek-chat", "你好", "你是测试助手")

    ok = logger._model_code == "deepseek-chat" and logger._provider_code == ""
    record(
        "logger.start() 接受 model_code 字符串",
        ok,
        f"model_code={logger._model_code}, provider_code='{logger._provider_code}'",
    )
    return ok


async def test_logger_bind_config_fills_provider_code():
    """bind_config() 在 resolve 成功后补全 provider_code。"""
    from app.services.ai_logger import AIChatLogger

    logger = AIChatLogger()
    logger.start("deepseek-chat", "你好", "你是测试助手")
    logger.bind_config(_FakeConfig())

    ok = logger._model_code == "deepseek-chat" and logger._provider_code == "deepseek"
    record(
        "logger.bind_config() 补全 provider_code",
        ok,
        f"model_code={logger._model_code}, provider_code={logger._provider_code}",
    )
    return ok


async def test_capability_failure_is_logged():
    """能力校验失败时，logger 要能记录 error 并 enqueue。"""
    from app.services.ai_logger import AIChatLogger
    from app.core.exceptions import BusinessException
    from app.services.log_queue import log_queue, LOG_TYPE_AI

    logger = AIChatLogger()
    logger.start("flash-special", "你好", None)

    captured: list[dict] = []
    original_enqueue = log_queue.enqueue

    def spy_enqueue(log_type: str, data: dict):
        captured.append({"log_type": log_type, "data": data})

    log_queue.enqueue = spy_enqueue
    try:
        try:
            raise BusinessException(code=400, message="该模型不支持思考模式")
        except BusinessException as e:
            logger.record_error(f"{type(e).__name__}: {e.message}")
            logger.enqueue()
    finally:
        log_queue.enqueue = original_enqueue

    if not captured:
        record("capability 失败写日志", False, "enqueue 未被调用")
        return False

    data = captured[0]["data"]
    ok = (
        data.get("model_code") == "flash-special"
        and data.get("is_error") is True
        and "不支持思考模式" in (data.get("error_message") or "")
    )
    record(
        "capability 失败写日志",
        ok,
        f"model_code={data.get('model_code')}, "
        f"is_error={data.get('is_error')}, "
        f"error_message={data.get('error_message')}",
    )
    return ok


class _FakeConfig:
    model_code = "deepseek-chat"
    provider_code = "deepseek"


# ─── 主流程 ──────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("测试: 超时机制 + usage 收集 + 能力校验失败写日志")
    print("=" * 60)

    await test_normal_iteration_ok()
    await test_timeout_triggers_on_slow_chunk()
    await test_timeout_on_first_chunk_stuck()
    await test_ai_logger_records_usage()
    await test_ai_logger_enqueue_writes_usage()
    await test_logger_start_accepts_model_code_string()
    await test_logger_bind_config_fills_provider_code()
    await test_capability_failure_is_logged()

    print()
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    print(f"结果: {passed}/{total} 通过")

    if passed < total:
        print("\n失败用例:")
        for r in results:
            if not r["passed"]:
                print(f"  - {r['name']}: {r['detail']}")
        sys.exit(1)
    else:
        print("全部通过 ✅")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
