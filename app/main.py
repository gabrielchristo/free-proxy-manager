import asyncio
import logging
import os
import tracemalloc
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app import __version__
from app.api.health import router as health_router
from app.api.proxies import router as proxies_router
from app.config import get_settings
from app.jobs.scheduler import JobScheduler
from app.logging import setup_logging

logger = logging.getLogger(__name__)
scheduler = JobScheduler()
_tracemalloc_tracing = False


def _tracemalloc_enabled() -> bool:
    return os.getenv("TRACEMALLOC") == "1"


def _log_tracemalloc_summary(label: str) -> None:
    if not _tracemalloc_tracing:
        return
    current, peak = tracemalloc.get_traced_memory()
    logger.info(
        "tracemalloc %s current=%.1fMB peak=%.1fMB",
        label,
        current / 1e6,
        peak / 1e6,
    )
    for stat in tracemalloc.take_snapshot().statistics("lineno")[:10]:
        logger.info("tracemalloc top: %s", stat)


async def _tracemalloc_report_loop(interval: int) -> None:
    while True:
        await asyncio.sleep(interval)
        _log_tracemalloc_summary("periodic")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    tracemalloc_task: asyncio.Task | None = None

    global _tracemalloc_tracing
    if _tracemalloc_enabled():
        tracemalloc.start(25)
        _tracemalloc_tracing = True
        interval_raw = os.getenv("TRACEMALLOC_INTERVAL", "60")
        try:
            interval = int(interval_raw)
        except ValueError:
            interval = 300
        if interval > 0:
            tracemalloc_task = asyncio.create_task(
                _tracemalloc_report_loop(interval),
                name="tracemalloc-report",
            )
        logger.info(
            "tracemalloc enabled frames=25 interval=%ss",
            interval if interval > 0 else "off",
        )

    await scheduler.start()
    yield
    await scheduler.stop()

    if tracemalloc_task is not None:
        tracemalloc_task.cancel()
        with suppress(asyncio.CancelledError):
            await tracemalloc_task
    _log_tracemalloc_summary("final")


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Discovery, validation and delivery of free HTTP/HTTPS proxies.",
        lifespan=lifespan,
    )
    application.include_router(proxies_router)
    application.include_router(health_router)
    return application


app = create_app()
