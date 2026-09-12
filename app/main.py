from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.health import router as health_router
from app.api.proxies import router as proxies_router
from app.config import get_settings
from app.jobs.scheduler import JobScheduler
from app.logging import setup_logging

scheduler = JobScheduler()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    await scheduler.start()
    yield
    await scheduler.stop()


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
