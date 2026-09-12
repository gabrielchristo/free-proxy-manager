import asyncio
import logging
from contextlib import suppress

from app.config import get_settings
from app.database import SessionLocal
from app.jobs.checker_job import CheckerJob
from app.jobs.cleanup_job import CleanupJob
from app.jobs.collector_job import CollectorJob
from app.jobs.score_job import ScoreJob

logger = logging.getLogger(__name__)


class JobScheduler:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.queue: asyncio.Queue[int | None] = asyncio.Queue()
        self.checker_job = CheckerJob(self.queue, self.settings)
        self.collector_job = CollectorJob()
        self.cleanup_job = CleanupJob(self.settings)
        self.score_job = ScoreJob()
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        await self.checker_job.start()
        self._tasks = [
            asyncio.create_task(self._collector_loop(), name="collector-loop"),
            asyncio.create_task(self._recheck_loop(), name="recheck-loop"),
            asyncio.create_task(self._cleanup_loop(), name="cleanup-loop"),
            asyncio.create_task(self._score_loop(), name="score-loop"),
        ]
        await self._run_initial_cycle()
        logger.info("Background jobs started")

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        await self.checker_job.stop()
        logger.info("Background jobs stopped")

    async def _run_initial_cycle(self) -> None:
        queued_ids = await self.collector_job.run()
        await self.checker_job.enqueue(queued_ids)

    async def _collector_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.collect_interval)
            queued_ids = await self.collector_job.run()
            await self.checker_job.enqueue(queued_ids)

    async def _recheck_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.recheck_interval)
            db = SessionLocal()
            try:
                count = await self.checker_job.enqueue_due_rechecks(db)
                logger.info("Recheck queued %s proxies", count)
            finally:
                db.close()

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.cleanup_interval)
            db = SessionLocal()
            try:
                self.cleanup_job.run(db)
            finally:
                db.close()

    async def _score_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.score_interval)
            db = SessionLocal()
            try:
                self.score_job.run(db)
            finally:
                db.close()
