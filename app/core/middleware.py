import time

from fastapi import FastAPI, Request


def register_middleware_handles(app: FastAPI):
    """
    注册中间件
    - 1. 记录请求处理时间的中间件
    """

    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        start_time = time.perf_counter()
        response = await call_next(request)
        process_time = time.perf_counter() - start_time
        # 添加自定义响应头
        response.headers["X-Process-Time"] = str(process_time)
        return response
