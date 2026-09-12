import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import SessionLocal
from app.models import Proxy, ProxyStatus
from app.services.checker import CheckerService, CheckResult
from app.services.scorer import ScorerService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProxyCheckTarget:
    proxy_id: int
    host: str
    port: int
    protocol: str
    url: str


class CheckerJob:
    def __init__(
        self,
        queue: asyncio.Queue[int | None],
        settings: Settings | None = None,
    ) -> None:
        self.queue = queue
        self.settings = settings or get_settings()
        self.checker = CheckerService(self.settings)
        self.scorer = ScorerService(self.settings)
        self._workers: list[asyncio.Task] = []
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        worker_count = self.settings.checker_concurrency
        self._workers = [
            asyncio.create_task(self._worker(index), name=f"checker-worker-{index}")
            for index in range(worker_count)
        ]
        logger.info("Checker workers started: %s", worker_count)

    async def stop(self) -> None:
        self._running = False
        for _ in self._workers:
            await self.queue.put(None)
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("Checker workers stopped")

    async def enqueue(self, proxy_ids: list[int]) -> None:
        for proxy_id in proxy_ids:
            await self.queue.put(proxy_id)

    async def enqueue_due_rechecks(self, db: Session) -> int:
        now = datetime.now(UTC)
        due = (
            db.query(Proxy.id)
            .filter(
                Proxy.status.in_(
                    [ProxyStatus.HEALTHY, ProxyStatus.DEGRADED, ProxyStatus.DEAD]
                ),
                (Proxy.cooldown_until.is_(None)) | (Proxy.cooldown_until <= now),
            )
            .limit(500)
            .all()
        )
        ids = [row[0] for row in due]
        await self.enqueue(ids)
        return len(ids)

    async def _worker(self, worker_id: int) -> None:
        while True:
            proxy_id = await self.queue.get()
            try:
                if proxy_id is None:
                    break
                await self._check_proxy(proxy_id)
            except Exception:
                logger.exception("Checker worker %s failed for proxy %s", worker_id, proxy_id)
            finally:
                self.queue.task_done()

    async def _check_proxy(self, proxy_id: int) -> None:
        target = self._mark_checking(proxy_id)
        if target is None:
            return

        result = await self.checker.check_proxy(
            host=target.host,
            port=target.port,
            protocol=target.protocol,
        )
        self._persist_result(target, result)

    def _mark_checking(self, proxy_id: int) -> ProxyCheckTarget | None:
        db = SessionLocal()
        try:
            proxy = db.query(Proxy).filter(Proxy.id == proxy_id).one_or_none()
            if proxy is None:
                return None

            proxy.status = ProxyStatus.CHECKING
            db.commit()
            return ProxyCheckTarget(
                proxy_id=proxy.id,
                host=proxy.host,
                port=proxy.port,
                protocol=proxy.protocol,
                url=proxy.url,
            )
        finally:
            db.close()

    def _persist_result(self, target: ProxyCheckTarget, result: CheckResult) -> None:
        db = SessionLocal()
        try:
            proxy = db.query(Proxy).filter(Proxy.id == target.proxy_id).one_or_none()
            if proxy is None:
                return

            self._apply_result(proxy, result)
            self.scorer.apply_to_proxy(proxy)
            db.commit()

            if result.success:
                logger.debug("Proxy %s healthy (score=%s)", target.url, proxy.score)
            else:
                logger.debug("Proxy %s failed: %s", target.url, result.error)
        finally:
            db.close()

    def _apply_result(self, proxy: Proxy, result: CheckResult) -> None:
        now = datetime.now(UTC)
        proxy.last_checked = now
        proxy.last_http_status = result.http_status
        proxy.latency_ms = result.latency_ms
        proxy.connect_time_ms = result.connect_time_ms

        if result.requires_auth:
            proxy.status = ProxyStatus.DISABLED
            proxy.failure_count += 1
            proxy.consecutive_failures += 1
            proxy.last_failure = now
            return

        if result.success:
            proxy.success_count += 1
            proxy.consecutive_failures = 0
            proxy.cooldown_until = None
            proxy.cooldown_level = 0
            proxy.last_success = now
            proxy.status = ProxyStatus.HEALTHY
            return

        proxy.failure_count += 1
        proxy.consecutive_failures += 1
        proxy.last_failure = now

        if proxy.consecutive_failures >= self.settings.failure_threshold:
            proxy.status = ProxyStatus.DEAD
            proxy.cooldown_level = min(proxy.cooldown_level + 1, 5)
            cooldown_seconds = min(
                self.settings.cooldown_initial * (2 ** (proxy.cooldown_level - 1)),
                self.settings.cooldown_max,
            )
            proxy.cooldown_until = now + timedelta(seconds=cooldown_seconds)
        else:
            proxy.status = ProxyStatus.DEGRADED
