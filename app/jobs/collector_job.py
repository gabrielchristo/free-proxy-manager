import asyncio
import logging

from app.services.collector import CollectorService

logger = logging.getLogger(__name__)


class CollectorJob:
    def __init__(self, collector: CollectorService | None = None) -> None:
        self.collector = collector or CollectorService()

    async def run(self) -> list[int]:
        logger.info("Collector job started")
        queued_ids = await self.collector.collect_all()
        logger.info("Collector job completed: %s proxies queued", len(queued_ids))
        return queued_ids
