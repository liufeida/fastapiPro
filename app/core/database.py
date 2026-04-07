from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

# 注意驱动使用 asyncpg
DATABASE_URL = "postgresql+asyncpg://postgres:123456@localhost:5432/mydb"

# 创建异步引擎
engine = create_async_engine(DATABASE_URL, echo=True)

# 创建异步会话工厂
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# 依赖注入：获取数据库会话
async def get_async_session():
    async with AsyncSessionLocal() as session:
        yield session


# lifespan 事件（替代 on_event）
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    # 关闭时释放连接池
    await engine.dispose()
