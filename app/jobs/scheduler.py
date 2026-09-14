import asyncio
import logging
from contextlib import suppress

from app.config import get_settings
from app.database import SessionLocal
from app.jobs.checkpoint_job import CheckpointJob
from app.jobs.checker_job import CheckerJob
from app.jobs.cleanup_job import CleanupJob
from app.jobs.collector_job import CollectorJob
from app.jobs.score_job import ScoreJob
from app.jobs.snapshot_job import SnapshotJob

logger = logging.getLogger(__name__)


class JobScheduler:
    """Coordinates background collector, checker, score, cleanup, and checkpoint loops."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.queue: asyncio.Queue[int | None] = asyncio.Queue(
            maxsize=self.settings.checker_queue_max_size
        )
        self.checker_job = CheckerJob(self.queue, self.settings)
        self.collector_job = CollectorJob()
        self.cleanup_job = CleanupJob(self.settings)
        self.score_job = ScoreJob()
        self.snapshot_job = SnapshotJob(self.settings)
        self.checkpoint_job = CheckpointJob(self.settings)
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start checker workers and periodic background tasks."""
        await self.checker_job.start()
        self._tasks = [
            asyncio.create_task(self._checker_refill_loop(), name="checker-refill-loop"),
            asyncio.create_task(self._collector_loop(), name="collector-loop"),
            asyncio.create_task(self._cleanup_loop(), name="cleanup-loop"),
            asyncio.create_task(self._score_loop(), name="score-loop"),
        ]
        if self.settings.db_checkpoint_interval > 0:
            self._tasks.append(
                asyncio.create_task(self._checkpoint_loop(), name="checkpoint-loop")
            )
        if self.settings.stats_snapshot_interval > 0:
            self._tasks.append(
                asyncio.create_task(self._snapshot_loop(), name="snapshot-loop")
            )
        await self._run_initial_cycle()
        logger.info("Background jobs started")

    async def stop(self) -> None:
        """Cancel loops and stop checker workers cleanly."""
        for task in self._tasks:
            task.cancel()
        await self.checker_job.stop()
        for task in self._tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        logger.info("Background jobs stopped")

    async def _run_initial_cycle(self) -> None:
        """Optionally collect on startup, then prime the checker queue."""
        if self.settings.collector_run_on_startup:
            await self.collector_job.run()
        else:
            logger.info(
                "Skipping initial collector run (COLLECTOR_RUN_ON_STARTUP=false); "
                "next collect in %ss",
                self.settings.collect_interval,
            )
        await self.checker_job.refill_queue()

    async def _checker_refill_loop(self) -> None:
        """Keep the checker queue filled; HEALTHY due for recheck get first priority."""
        while True:
            await self.checker_job.refill_queue()
            await asyncio.sleep(self.settings.checker_refill_interval)

    async def _collector_loop(self) -> None:
        """Run source collection on a fixed interval."""
        while True:
            await asyncio.sleep(self.settings.collect_interval)
            await self.collector_job.run()

    async def _cleanup_loop(self) -> None:
        """Remove stale dead proxies that never succeeded."""
        while True:
            await asyncio.sleep(self.settings.cleanup_interval)
            removed = await asyncio.to_thread(self._run_cleanup_job)
            if removed:
                logger.info("Cleanup removed %s stale proxies", removed)

    async def _score_loop(self) -> None:
        """Recalculate proxy scores in batches."""
        while True:
            await asyncio.sleep(self.settings.score_interval)
            updated = await asyncio.to_thread(self._run_score_job)
            logger.info("Score recalculation completed for %s proxies", updated)

    async def _checkpoint_loop(self) -> None:
        """Run SQLite WAL checkpoints on a fixed interval."""
        while True:
            await asyncio.sleep(self.settings.db_checkpoint_interval)
            await asyncio.to_thread(self.checkpoint_job.run)

    async def _snapshot_loop(self) -> None:
        """Persist pool status counts for historical charts."""
        while True:
            await asyncio.to_thread(self._run_snapshot_job)
            await asyncio.sleep(self.settings.stats_snapshot_interval)

    def _run_cleanup_job(self) -> int:
        """Execute cleanup inside a short-lived DB session."""
        db = SessionLocal()
        try:
            return self.cleanup_job.run(db)
        finally:
            db.close()

    def _run_score_job(self) -> int:
        """Execute score recalculation inside a short-lived DB session."""
        db = SessionLocal()
        try:
            return self.score_job.run(db)
        finally:
            db.close()

    def _run_snapshot_job(self) -> None:
        """Record a pool snapshot inside a short-lived DB session."""
        db = SessionLocal()
        try:
            self.snapshot_job.run(db)
        finally:
            db.close()
