"""
Task 8 黑盒测试脚本 — Prompt CRUD + 日志队列 + 脱敏 + 缓存刷新

运行：.venv\\Scripts\\python.exe test_pipeline.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import traceback
from typing import Any

import httpx

BASE_URL = "http://127.0.0.1:8765"
FLUSH_WAIT = 3.0

results: list[dict[str, Any]] = []


def record(name: str, passed: bool, detail: str = "") -> None:
    results.append({"name": name, "passed": passed, "detail": detail})
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}")
    if detail:
        for line in detail.strip().splitlines():
            print(f"         {line}")


async def sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def _find_log_by_body(client: httpx.AsyncClient, body_marker: str, page_size: int = 50) -> dict | None:
    """在 api_access_log 中查找 request_body 包含指定 marker 的最新日志。"""
    r = await client.post("/api/logs/api/list", json={"page": 1, "pageSize": page_size})
    records = r.json().get("data", {}).get("records", [])
    for rec in records:
        rb = rec.get("request_body") or ""
        if body_marker in rb:
            return rec
    return None


async def _find_ai_log_by_trace(client: httpx.AsyncClient, trace_id: str) -> dict | None:
    """在 ai_chat_log 中查找指定 trace_id 的日志。"""
    r = await client.post("/api/logs/ai/list", json={"page": 1, "pageSize": 50})
    records = r.json().get("data", {}).get("records", [])
    for rec in records:
        if rec.get("trace_id") == trace_id:
            return rec
    return None


async def test_prompt_crud(client: httpx.AsyncClient) -> None:
    section = "测试 1: Prompt CRUD 全流程"
    print(f"\n{'='*60}\n{section}\n{'='*60}")
    prompt_id = None

    try:
        create_payload = {
            "name": "全局默认对话",
            "prompt_code": "global_chat_default",
            "content": "你是一个乐于助人的 AI 助手。",
            "model_code": None,
            "is_default": True,
            "is_enabled": True,
            "sort_order": 0,
        }
        r = await client.post("/api/prompts", json=create_payload)
        body = r.json()
        record("1.1 POST /api/prompts 200", r.status_code == 200,
               detail=f"status={r.status_code}, body={json.dumps(body, ensure_ascii=False)[:300]}")

        data = body.get("data", {})
        prompt_id = data.get("id")
        record("1.2 创建返回 data.id", bool(prompt_id), detail=f"id={prompt_id}")

        r2 = await client.post("/api/prompts/list", json={"page": 1, "pageSize": 10})
        body2 = r2.json()
        record("1.3 POST /api/prompts/list 200", r2.status_code == 200,
               detail=f"total={body2.get('data', {}).get('total')}")

        records = body2.get("data", {}).get("records", [])
        found = any(rec.get("id") == prompt_id for rec in records)
        record("1.4 list 包含刚创建的记录", found)

        r3 = await client.get(f"/api/prompts/{prompt_id}")
        body3 = r3.json()
        record("1.5 GET /api/prompts/{id} 200", r3.status_code == 200,
               detail=f"content={body3.get('data', {}).get('content', '')[:50]}")

        r4 = await client.patch(f"/api/prompts/{prompt_id}",
                                json={"content": "你是一个专业的编程助手。"})
        body4 = r4.json()
        record("1.6 PATCH /api/prompts/{id} 200", r4.status_code == 200,
               detail=f"new_content={body4.get('data', {}).get('content', '')[:50]}")

        r5 = await client.delete(f"/api/prompts/{prompt_id}")
        record("1.7 DELETE /api/prompts/{id} 200", r5.status_code == 200)

        await sleep(1)
        r6 = await client.post("/api/prompts/list", json={"page": 1, "pageSize": 10})
        records_after = r6.json().get("data", {}).get("records", [])
        found_after = any(rec.get("id") == prompt_id for rec in records_after)
        record("1.8 软删除后 list 不再返回该条", not found_after,
               detail=f"total={r6.json().get('data', {}).get('total')}")

    except Exception as e:
        record("测试 1 异常", False, detail=f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


async def test_api_logging(client: httpx.AsyncClient) -> str | None:
    section = "测试 2: HTTP API 日志记录验证"
    print(f"\n{'='*60}\n{section}\n{'='*60}")
    unique_code = f"testlog_{int(time.time())}"
    trace_id = None

    try:
        create_payload = {
            "name": "日志测试 Prompt",
            "prompt_code": unique_code,
            "content": "这是一条用于测试日志记录的 prompt 内容。",
            "model_code": None,
            "is_default": False,
            "is_enabled": True,
            "sort_order": 1,
        }
        r = await client.post("/api/prompts", json=create_payload)
        record("2.1 创建 Prompt 触发日志", r.status_code == 200)

        print(f"  → 等待 log_queue flush ({FLUSH_WAIT}s)...")
        await sleep(FLUSH_WAIT)

        target_log = await _find_log_by_body(client, unique_code)
        record("2.2 找到包含 unique_code 的 api_log", target_log is not None,
               detail=f"unique_code={unique_code}")

        if target_log:
            record("2.3 path 包含 /prompts", "/prompts" in target_log.get("path", ""),
                   detail=f"path={target_log.get('path')}, method={target_log.get('method')}")
            record("2.4 response_status = 200", target_log.get("response_status") == 200,
                   detail=f"response_status={target_log.get('response_status')}")
            rb = target_log.get("request_body") or ""
            record("2.5 request_body 包含 prompt_code", unique_code in rb,
                   detail=f"request_body_snippet={rb[:200]}")
            record("2.6 trace_id 非空", bool(target_log.get("trace_id")),
                   detail=f"trace_id={target_log.get('trace_id')}")
            trace_id = target_log.get("trace_id")
        else:
            record("2.3~2.6 无法定位目标日志", False, detail="没找到带 unique_code 的日志")

    except Exception as e:
        record("测试 2 异常", False, detail=f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

    return trace_id


async def test_ai_chat_log(client: httpx.AsyncClient) -> str | None:
    section = "测试 3: AI 调用日志"
    print(f"\n{'='*60}\n{section}\n{'='*60}")
    chat_trace_id = None

    try:
        r_health = await client.get("/api/ai/health")
        health_data = r_health.json().get("data", {})
        enabled_count = health_data.get("enabled_count", 0)
        providers = health_data.get("providers", [])
        record("3.1 /api/ai/health 可访问", r_health.status_code == 200,
               detail=f"enabled_count={enabled_count}, providers={providers}")

        if enabled_count == 0:
            record("3.2 跳过 AI 调用（无启用模型）", True)
            try:
                from app.services.ai.dispatcher import ai_dispatcher  # noqa: F401
                from app.services.ai_logger import AIChatLogger, wrap_stream_for_logging  # noqa: F401
                record("3.3 dispatcher + ai_logger import 无报错", True)
            except Exception as e:
                record("3.3 dispatcher + ai_logger import 无报错", False, detail=str(e))
            return None

        r_models = await client.post("/api/ai-models/list", json={"page": 1, "pageSize": 10})
        enabled_models = [m for m in r_models.json().get("data", {}).get("records", []) if m.get("is_enabled")]
        if not enabled_models:
            record("3.2 跳过（无启用模型）", True)
            return None

        target_model = enabled_models[0]["model_code"]
        record(f"3.2 尝试 AI chat (model={target_model})", True)

        chat_payload = {"model": target_model, "prompt": "说一个字：好", "thinking": False}
        r_chat = await client.post("/api/ai/chat", json=chat_payload, timeout=30.0)
        record("3.3 /api/ai/chat 200", r_chat.status_code == 200,
               detail=f"body={r_chat.text[:200]}")

        await sleep(FLUSH_WAIT)

        r_logs = await client.post("/api/logs/api/list", json={"page": 1, "pageSize": 50})
        api_records = r_logs.json().get("data", {}).get("records", [])
        chat_api_log = next((r for r in api_records if "/ai/chat" in r.get("path", "") and r.get("method") == "POST"), None)
        if chat_api_log:
            chat_trace_id = chat_api_log.get("trace_id")
            record("3.4 找到 AI chat 对应的 api_log", True,
                   detail=f"trace_id={chat_trace_id}")
        else:
            record("3.4 找到 AI chat 对应的 api_log", False, detail="没找到 POST /ai/chat 的 api_log")

        if chat_trace_id:
            ai_log = await _find_ai_log_by_trace(client, chat_trace_id)
            record("3.5 ai_chat_log 有对应 trace_id 的记录", ai_log is not None,
                   detail=f"trace_id={chat_trace_id}")
            if ai_log:
                record("3.6 ai_log trace_id 非空", bool(ai_log.get("trace_id")))
                record("3.7 system_prompt 非空", bool(ai_log.get("system_prompt")),
                       detail=f"system_prompt_snippet={(ai_log.get('system_prompt') or '')[:100]}")
                record("3.8 response_content 有值", bool(ai_log.get("response_content")),
                       detail=f"response={ai_log.get('response_content', '')[:50]}")
                record("3.9 duration_ms > 0", (ai_log.get("duration_ms") or 0) > 0,
                       detail=f"duration_ms={ai_log.get('duration_ms')}")

    except Exception as e:
        record("测试 3 异常", False, detail=f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

    return chat_trace_id


async def test_sensitive_data_masking(client: httpx.AsyncClient) -> None:
    section = "测试 4: 敏感数据脱敏验证"
    print(f"\n{'='*60}\n{section}\n{'='*60}")

    try:
        unique_code = f"masktest_{int(time.time())}"
        payload = {
            "name": "脱敏测试 Prompt",
            "prompt_code": unique_code,
            "content": "测试敏感数据脱敏",
            "model_code": None,
            "is_default": False,
            "is_enabled": True,
            "sort_order": 1,
            "api_key": "sk-secret-value-12345",
            "password": "my-super-secret-pwd",
            "authorization": "Bearer sk-auth-token-abc",
        }
        r = await client.post("/api/prompts", json=payload)
        record("4.1 发送带敏感字段的请求", True, detail=f"status={r.status_code}")

        await sleep(FLUSH_WAIT)

        target_log = await _find_log_by_body(client, unique_code)
        record("4.2 找到对应 api_log", target_log is not None)

        if target_log:
            rb = target_log.get("request_body") or ""
            record("4.3 api_key 明文被替换", "sk-secret-value-12345" not in rb,
                   detail=f"has_plain={'sk-secret-value-12345' in rb}, has_mask={'***' in rb}, rb={rb[:250]}")
            record("4.4 password 明文被替换", "my-super-secret-pwd" not in rb,
                   detail=f"has_plain={'my-super-secret-pwd' in rb}")
            record("4.5 authorization 明文被替换", "sk-auth-token-abc" not in rb,
                   detail=f"has_plain={'sk-auth-token-abc' in rb}")
            record("4.6 脱敏标记 *** 出现", "***" in rb, detail=f"rb={rb[:300]}")

    except Exception as e:
        record("测试 4 异常", False, detail=f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


async def test_prompt_cache_refresh(client: httpx.AsyncClient) -> None:
    section = "测试 5: Prompt 缓存刷新生效"
    print(f"\n{'='*60}\n{section}\n{'='*60}")
    prompt_id = None

    try:
        create_payload = {
            "name": "缓存测试 Prompt",
            "prompt_code": "cache_refresh_test",
            "content": "PROMPT_V1",
            "model_code": None,
            "is_default": True,
            "is_enabled": True,
            "sort_order": 0,
        }
        r1 = await client.post("/api/prompts", json=create_payload)
        record("5.1 创建 V1 Prompt", r1.status_code == 200)
        prompt_id = r1.json().get("data", {}).get("id")

        r2 = await client.patch(f"/api/prompts/{prompt_id}", json={"content": "PROMPT_V2"})
        body2 = r2.json()
        new_content = body2.get("data", {}).get("content")
        record("5.2 PATCH 更新为 PROMPT_V2",
               r2.status_code == 200 and new_content == "PROMPT_V2",
               detail=f"new_content={new_content}")

        await sleep(FLUSH_WAIT)

        r_health = await client.get("/api/ai/health")
        enabled_count = r_health.json().get("data", {}).get("enabled_count", 0)

        if enabled_count > 0:
            r_models = await client.post("/api/ai-models/list", json={"page": 1, "pageSize": 10})
            models = [m for m in r_models.json().get("data", {}).get("records", []) if m.get("is_enabled")]
            if models:
                target = models[0]["model_code"]
                before_count = (await client.post("/api/logs/ai/list", json={"page": 1, "pageSize": 1})).json().get("data", {}).get("total", 0)

                r_chat = await client.post("/api/ai/chat", json={
                    "model": target, "prompt": "test cache refresh",
                }, timeout=30.0)
                record("5.3 触发 AI 调用", r_chat.status_code == 200,
                       detail=f"chat_status={r_chat.status_code}")
                await sleep(FLUSH_WAIT)

                after_count = (await client.post("/api/logs/ai/list", json={"page": 1, "pageSize": 1})).json().get("data", {}).get("total", 0)
                record("5.4 产生新 ai_log", after_count > before_count,
                       detail=f"before={before_count}, after={after_count}")

                if after_count > before_count:
                    new_ai_log = (await client.post("/api/logs/ai/list", json={"page": 1, "pageSize": 5})).json().get("data", {}).get("records", [])
                    if new_ai_log:
                        sp = new_ai_log[0].get("system_prompt") or ""
                        record("5.5 最新 ai_log system_prompt 包含 PROMPT_V2",
                               "PROMPT_V2" in sp,
                               detail=f"V2_in={'PROMPT_V2' in sp}, V1_in={'PROMPT_V1' in sp}, sp={sp[:250]}")
                        record("5.6 system_prompt 不包含 PROMPT_V1", "PROMPT_V1" not in sp)
        else:
            r_enabled = await client.get("/api/prompts/enabled")
            enabled_list = r_enabled.json().get("data", [])
            cache_prompt = next((p for p in enabled_list if p.get("prompt_code") == "cache_refresh_test"), None)
            if cache_prompt:
                record("5.3 DB 中 Prompt 已更新为 PROMPT_V2",
                       cache_prompt.get("content") == "PROMPT_V2",
                       detail=f"content={cache_prompt.get('content')}")
            else:
                record("5.3 DB 侧面验证", False, detail="enabled 列表未找到 cache_refresh_test")

    except Exception as e:
        record("测试 5 异常", False, detail=f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
    finally:
        if prompt_id:
            try:
                await client.delete(f"/api/prompts/{prompt_id}")
            except Exception:
                pass


async def test_log_pagination_and_detail(client: httpx.AsyncClient) -> None:
    section = "测试 6: 日志分页和筛选"
    print(f"\n{'='*60}\n{section}\n{'='*60}")

    try:
        r1 = await client.post("/api/logs/api/list", json={"page": 1, "pageSize": 5})
        data1 = r1.json().get("data", {})
        record("6.1 api logs list 200", r1.status_code == 200,
               detail=f"records={len(data1.get('records', []))}, total={data1.get('total')}, pages={data1.get('pages')}")
        if data1.get("records"):
            first_id = data1["records"][0].get("id")
            r2 = await client.get(f"/api/logs/api/{first_id}")
            detail_data = r2.json().get("data", {})
            record("6.2 GET /api/logs/api/{id} 200", r2.status_code == 200)
            record("6.3 详情接口 request_body 存在",
                   "request_body" in detail_data,
                   detail=f"request_body_len={len(detail_data.get('request_body') or '')}")
            record("6.4 created_at 非空（已修复 NULL 问题）",
                   bool(detail_data.get("created_at")),
                   detail=f"created_at={detail_data.get('created_at')}")

        r3 = await client.post("/api/logs/api/list", json={"page": 1, "pageSize": 5, "response_status": 200})
        records3 = r3.json().get("data", {}).get("records", [])
        all_200 = all(rec.get("response_status") == 200 for rec in records3) if records3 else True
        record("6.5 筛选 response_status=200", all_200,
               detail=f"filtered_count={len(records3)}, all_200={all_200}")

        r4 = await client.post("/api/logs/ai/list", json={"page": 1, "pageSize": 5})
        data4 = r4.json().get("data", {})
        record("6.6 ai logs list 200", r4.status_code == 200,
               detail=f"records={len(data4.get('records', []))}, total={data4.get('total')}")
        if data4.get("records"):
            ai_first_id = data4["records"][0].get("id")
            r5 = await client.get(f"/api/logs/ai/{ai_first_id}")
            record("6.7 GET /api/logs/ai/{id} 200", r5.status_code == 200,
                   detail=f"ai_detail_keys={list(r5.json().get('data', {}).keys())[:10]}")

    except Exception as e:
        record("测试 6 异常", False, detail=f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


async def main() -> None:
    print("=" * 70)
    print("  Task 8 黑盒测试 — Prompt CRUD + 日志 + 脱敏 + 缓存")
    print(f"  target: {BASE_URL}")
    print("=" * 70)

    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=timeout) as client:
        try:
            r = await client.get("/api/ai/health")
            print(f"\n[info] 健康检查 status={r.status_code}, body={r.text[:200]}")
        except httpx.ConnectError as e:
            print(f"[FATAL] 无法连接 {BASE_URL}: {e}")
            sys.exit(1)

        await test_prompt_crud(client)
        await test_api_logging(client)
        await test_ai_chat_log(client)
        await test_sensitive_data_masking(client)
        await test_prompt_cache_refresh(client)
        await test_log_pagination_and_detail(client)

    print("\n" + "=" * 70)
    print("  测试汇总")
    print("=" * 70)
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    for r in results:
        tag = "PASS" if r["passed"] else "FAIL"
        print(f"  [{tag}] {r['name']}")
        if not r["passed"] and r["detail"]:
            for line in r["detail"].strip().splitlines():
                print(f"         {line}")
    print(f"\n  结果: {passed}/{total} tests passed")
    print("=" * 70)

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
