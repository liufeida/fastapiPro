import time
from typing import Any, Optional

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.core.database import lifespan

from .api.v1 import api


class ErrorResponse(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


app = FastAPI(lifespan=lifespan)

# 访问静态资源：http://127.0.0.1:8000/uploads/...
app.mount("/uploads", StaticFiles(directory="uploads"), name="static_files")

app.include_router(api.router)

origins = [
    "http://localhost",
    "http://localhost:9527",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc: Exception):
    # 可以记录日志
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="服务器内部错误",
            data=None,
        ).model_dump(),
    )
