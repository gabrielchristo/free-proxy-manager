import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.datetime_utils import as_utc, utc_now
from app.database import SessionLocal
from app.models import Proxy, ProxySource, ProxySourceLink, ProxyStatus
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
    source_label: str
    previous_status: str


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
        now = utc_now()
        due = (
            db.query(Proxy.id)
            .filter(
                Proxy.status.in_(
                    [ProxyStatus.HEALTHY, ProxyStatus.DEGRADED, ProxyStatus.DEAD]
                ),
                (Proxy.cooldown_until.is_(None)) | (Proxy.cooldown_until <= now),
            )
            .limit(self.settings.recheck_batch_size)
            .all()
        )
        ids = [row[0] for row in due]
        await self.enqueue(ids)
        logger.info("Recheck enqueued proxies=%s", len(ids))
        return len(ids)

    async def _worker(self, worker_id: int) -> None:
        while True:
            proxy_id = await self.queue.get()
            try:
                if proxy_id is None:
                    break
                await self._check_proxy(proxy_id)
            except Exception:
                logger.exception("Checker worker %s failed for proxy_id=%s", worker_id, proxy_id)
            finally:
                self.queue.task_done()

    async def _check_proxy(self, proxy_id: int) -> None:
        target = self._mark_checking(proxy_id)
        if target is None:
            return

        logger.info(
            "[%s] Checking proxy %s",
            target.source_label,
            target.url,
        )
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

            source_label = self._resolve_source_label(db, proxy_id)
            previous_status = proxy.status.value
            proxy.status = ProxyStatus.CHECKING
            db.commit()
            return ProxyCheckTarget(
                proxy_id=proxy.id,
                host=proxy.host,
                port=proxy.port,
                protocol=proxy.protocol,
                url=proxy.url,
                source_label=source_label,
                previous_status=previous_status,
            )
        finally:
            db.close()

    def _persist_result(self, target: ProxyCheckTarget, result: CheckResult) -> None:
        db = SessionLocal()
        try:
            proxy = db.query(Proxy).filter(Proxy.id == target.proxy_id).one_or_none()
            if proxy is None:
                return

            previous_status = target.previous_status
            self._apply_result(proxy, result)
            self.scorer.apply_to_proxy(proxy)
            db.commit()

            if (
                not result.success
                and proxy.status == ProxyStatus.DEAD
                and proxy.cooldown_until is not None
            ):
                logger.info(
                    "[%s] Proxy %s entered cooldown until=%s level=%s",
                    target.source_label,
                    target.url,
                    proxy.cooldown_until.isoformat(),
                    proxy.cooldown_level,
                )

            if result.success:
                logger.info(
                    "[%s] Proxy %s check succeeded status=%s->%s http=%s latency_ms=%s score=%s",
                    target.source_label,
                    target.url,
                    previous_status,
                    proxy.status.value,
                    result.http_status,
                    result.latency_ms,
                    proxy.score,
                )
                return

            logger.info(
                "[%s] Proxy %s check failed status=%s->%s error=%s http=%s latency_ms=%s requires_auth=%s",
                target.source_label,
                target.url,
                previous_status,
                proxy.status.value,
                result.error,
                result.http_status,
                result.latency_ms,
                result.requires_auth,
            )
        finally:
            db.close()

    @staticmethod
    def _resolve_source_label(db: Session, proxy_id: int) -> str:
        rows = (
            db.query(ProxySource.name)
            .join(ProxySourceLink, ProxySourceLink.source_id == ProxySource.id)
            .filter(ProxySourceLink.proxy_id == proxy_id)
            .order_by(ProxySource.priority.desc(), ProxySource.name.asc())
            .all()
        )
        if not rows:
            return "unknown"
        return ", ".join(row[0] for row in rows)

    def _apply_result(self, proxy: Proxy, result: CheckResult) -> None:
        now = utc_now()
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
            proxy.cooldown_level = min(proxy.cooldown_level + 1, self.settings.cooldown_max_level)
            cooldown_seconds = min(
                self.settings.cooldown_initial * (2 ** (proxy.cooldown_level - 1)),
                self.settings.cooldown_max,
            )
            proxy.cooldown_until = now + timedelta(seconds=cooldown_seconds)
        else:
            proxy.status = ProxyStatus.DEGRADED
