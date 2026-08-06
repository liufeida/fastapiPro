import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.services.prompt_cache import prompt_cache

# 注意驱动使用 asyncpg
DATABASE_URL = "postgresql+asyncpg://postgres:123456@localhost:5432/mydb"

# 创建异步引擎
engine = create_async_engine(DATABASE_URL, echo=False)

# 创建异步会话工厂
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# 依赖注入：获取数据库会话
async def get_async_session():
    async with AsyncSessionLocal() as session:
        yield session


# lifespan 事件（替代 on_event）
@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.log_queue import log_queue

    # 启动时创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    # 启动日志队列后台 flush
    await log_queue.start()

    # 启动时加载 Prompt 缓存
    try:
        async with AsyncSessionLocal() as session:
            await prompt_cache.warm_up(session)
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"Prompt cache warm_up failed (tables may not exist yet): {e}"
        )
    yield

    # 关闭时停止日志队列（强制 flush 剩余）
    await log_queue.stop()

    # 关闭时释放连接池
    await engine.dispose()
