import time
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.core.database import lifespan
from app.core.exceptions import register_exception_handlers

from .api.v1 import api


class ErrorResponse(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


app = FastAPI(lifespan=lifespan)

register_exception_handlers(app)

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
    # 添加自定义响应头
    response.headers["X-Process-Time"] = str(process_time)
    return response
