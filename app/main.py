from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.database import lifespan
from app.core.exceptions import register_exception_handlers
from app.core.middleware import register_middleware_handles

from .api.v1 import api

app = FastAPI(lifespan=lifespan)

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
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
