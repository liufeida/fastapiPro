import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import insert
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import AsyncSessionLocal, engine

logger = logging.getLogger(__name__)

LOG_TYPE_API = "api_access_log"
LOG_TYPE_AI = "ai_chat_log"

FLUSH_INTERVAL_SECONDS = 2.0
FLUSH_BATCH_SIZE = 50


class LogQueue:
    """异步日志队列——fire-and-forget 写入 DB。"""

    def __init__(self):
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._flush_task: asyncio.Task | None = None
        self._running = False

    def enqueue(self, log_type: str, data: dict[str, Any]) -> None:
        """放入一条日志记录（非阻塞）。"""
        try:
            enriched = {
                "_type": log_type,
                "created_at": datetime.now(timezone.utc),
                **data,
            }
            self._queue.put_nowait(enriched)
        except asyncio.QueueFull:
            logger.warning("LogQueue is full, dropping a log record")

    async def start(self) -> None:
        """启动后台 flush 协程。"""
        if self._running:
            return
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("LogQueue background flush started")

    async def stop(self) -> None:
        """停止后台协程并强制 flush 剩余队列。"""
        self._running = False
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
        await self._flush_remaining()
        logger.info("LogQueue stopped, remaining records flushed")

    async def _flush_loop(self) -> None:
        """后台循环：定时或批量触发 flush。"""
        try:
            while self._running:
                await asyncio.sleep(FLUSH_INTERVAL_SECONDS)
                if self._queue.qsize() >= FLUSH_BATCH_SIZE or self._queue.qsize() > 0:
                    await self._flush_remaining()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("LogQueue flush_loop error")

    async def _flush_remaining(self) -> None:
        """将队列中所有记录一次性写入 DB。"""
        records: list[dict] = []
        while not self._queue.empty():
            try:
                records.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if not records:
            return

        api_records = [r for r in records if r.get("_type") == LOG_TYPE_API]
        ai_records = [r for r in records if r.get("_type") == LOG_TYPE_AI]

        try:
            async with AsyncSessionLocal() as session:
                if api_records:
                    from app.models.api_access_log import ApiAccessLog
                    clean = [{k: v for k, v in r.items() if k != "_type"} for r in api_records]
                    stmt = insert(ApiAccessLog).values(clean)
                    await session.execute(stmt)
                    logger.info(f"Flushed {len(api_records)} api_access_log records")
                if ai_records:
                    from app.models.ai_chat_log import AIChatLog
                    clean = [{k: v for k, v in r.items() if k != "_type"} for r in ai_records]
                    stmt = insert(AIChatLog).values(clean)
                    await session.execute(stmt)
                    logger.info(f"Flushed {len(ai_records)} ai_chat_log records")
                await session.commit()
        except Exception:
            logger.exception("LogQueue batch flush failed")


log_queue = LogQueue()
