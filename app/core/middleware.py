import json
import logging
import time
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from app.core.trace import generate_trace_id
from app.services.log_queue import LOG_TYPE_API, log_queue

logger = logging.getLogger(__name__)

SKIP_LOG_PREFIXES = ("/api/v1/logs/", "/api/docs", "/api/openapi.json")

SENSITIVE_KEYS = ("api_key", "apikey", "api-key", "authorization", "token", "secret", "password")


def _mask_sensitive(text: str | None) -> str | None:
    if not text:
        return text
    try:
        data = json.loads(text)
        _mask_obj(data)
        return json.dumps(data, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        return text


def _mask_obj(obj) -> None:
    if isinstance(obj, dict):
        for key in list(obj.keys()):
            key_lower = key.lower()
            if any(s in key_lower for s in SENSITIVE_KEYS):
                obj[key] = "***"
            else:
                _mask_obj(obj[key])
    elif isinstance(obj, list):
        for item in obj:
            _mask_obj(item)


def _is_skip_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in SKIP_LOG_PREFIXES)


def _get_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def register_middleware_handles(app: FastAPI):
    """注册中间件。"""

    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        start_time = time.perf_counter()
        response = await call_next(request)
        process_time = time.perf_counter() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        return response

    @app.middleware("http")
    async def api_access_log_middleware(request: Request, call_next):
        if _is_skip_path(request.url.path):
            return await call_next(request)

        trace_id = generate_trace_id()
        start_time = time.perf_counter()
        request_body_str: str | None = None
        response_body_str: str | None = None
        is_streaming = False
        is_error = False
        error_message: str | None = None
        response_status = 0

        try:
            raw_body = await request.body()
            request_body_str = raw_body.decode("utf-8", errors="replace") if raw_body else None
        except Exception:
            request_body_str = None

        query_params_str = None
        if request.url.query:
            query_params_str = json.dumps(dict(request.query_params), ensure_ascii=False)

        try:
            response = await call_next(request)
            response_status = response.status_code

            is_streaming = isinstance(response, StreamingResponse) or hasattr(response, "body_iterator")

            if is_streaming:
                original_iterator = response.body_iterator

                async def stream_wrapper() -> AsyncIterator[bytes]:
                    first_chunks: list[bytes] = []
                    chunk_count = 0
                    max_preview_bytes = 500

                    async for chunk in original_iterator:
                        yield chunk
                        chunk_count += 1
                        if len(first_chunks) < 3:
                            first_chunks.append(chunk)
                        elif sum(len(c) for c in first_chunks) < max_preview_bytes:
                            first_chunks.append(chunk)
                            if sum(len(c) for c in first_chunks) >= max_preview_bytes:
                                break

                    elapsed = (time.perf_counter() - start_time) * 1000
                    preview = b"".join(first_chunks).decode("utf-8", errors="replace")
                    resp_abstract = f"(streaming, {chunk_count} chunks) {preview[:200]}"
                    log_queue.enqueue(LOG_TYPE_API, {
                        "trace_id": trace_id,
                        "method": request.method,
                        "path": request.url.path,
                        "query_params": query_params_str,
                        "request_body": _mask_sensitive(request_body_str),
                        "response_status": response_status,
                        "response_body": resp_abstract[:500],
                        "duration_ms": round(elapsed, 2),
                        "is_streaming": True,
                        "is_error": False,
                        "error_message": None,
                        "ip": _get_client_ip(request),
                        "user_agent": request.headers.get("user-agent"),
                    })

                response.body_iterator = stream_wrapper()
            else:
                body_chunks: list[bytes] = []
                async for chunk in response.body_iterator:
                    body_chunks.append(chunk)
                full_body = b"".join(body_chunks)
                response_body_str = full_body.decode("utf-8", errors="replace")

                from fastapi.responses import Response as FastAPIResponse
                new_response = FastAPIResponse(
                    content=full_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )
                response = new_response

                elapsed = (time.perf_counter() - start_time) * 1000
                log_queue.enqueue(LOG_TYPE_API, {
                    "trace_id": trace_id,
                    "method": request.method,
                    "path": request.url.path,
                    "query_params": query_params_str,
                    "request_body": _mask_sensitive(request_body_str),
                    "response_status": response_status,
                    "response_body": _mask_sensitive(response_body_str),
                    "duration_ms": round(elapsed, 2),
                    "is_streaming": False,
                    "is_error": False,
                    "error_message": None,
                    "ip": _get_client_ip(request),
                    "user_agent": request.headers.get("user-agent"),
                })

        except Exception as exc:
            is_error = True
            error_message = f"{type(exc).__name__}: {str(exc)}"
            response_status = 500
            elapsed = (time.perf_counter() - start_time) * 1000
            log_queue.enqueue(LOG_TYPE_API, {
                "trace_id": trace_id,
                "method": request.method,
                "path": request.url.path,
                "query_params": query_params_str,
                "request_body": _mask_sensitive(request_body_str),
                "response_status": response_status,
                "response_body": None,
                "duration_ms": round(elapsed, 2),
                "is_streaming": False,
                "is_error": True,
                "error_message": error_message[:2000],
                "ip": _get_client_ip(request),
                "user_agent": request.headers.get("user-agent"),
            })
            raise

        return response
