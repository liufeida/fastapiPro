import logging

from dotenv import load_dotenv

# 加载项目根目录 .env 文件，必须在导入业务模块之前执行
load_dotenv()

# 配置日志：在导入业务模块之前执行，确保所有 logger 都能输出
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# 屏蔽第三方噪音日志，只保留 WARNING 及以上
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.database import lifespan
from app.core.exceptions import register_exception_handlers
from app.core.middleware import register_middleware_handles

from .api.v1 import api

# 导入 AI 服务包，触发 provider 注册副作用（deepseek/ollama 等）
from app.services import ai as _ai_services  # noqa: F401

app = FastAPI(
    lifespan=lifespan,
    root_path="/api",
    # servers=["http://http://127.0.0.1:8000/"],
    # docs_url="/api/docs",
    # openapi_url="/api/openapi.json",
)

register_exception_handlers(app)
register_middleware_handles(app)

# 访问静态资源：http://127.0.0.1:8000/uploads/...
app.mount("/uploads", StaticFiles(directory="uploads"), name="static_files")

app.include_router(api.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:9527",
        "http://localhost:3000",
        "https://web.agentcore.art",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
