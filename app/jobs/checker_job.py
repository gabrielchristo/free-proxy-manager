import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.datetime_utils import format_log_datetime, utc_now
from app.database import SessionLocal
from app.models import Proxy, ProxySource, ProxySourceLink, ProxyStatus
from app.services.checker import CheckerService, CheckResult
from app.services.connectivity import ConnectivityGuard
from app.services.scorer import ScorerService

logger = logging.getLogger(__name__)

QUEUE_STATE_ORDER = ("healthy", "new", "degraded", "dead")


@dataclass(frozen=True, slots=True)
class ProxyCheckTarget:
    """Snapshot of a proxy loaded before the HTTP check runs."""

    proxy_id: int
    host: str
    port: int
    protocol: str
    url: str
    source_label: str
    previous_status: str


class CheckerJob:
    """Runs concurrent proxy checks via a bounded asyncio queue."""

    def __init__(
        self,
        queue: asyncio.Queue[int | None],
        settings: Settings | None = None,
    ) -> None:
        self.queue = queue
        self.settings = settings or get_settings()
        self.checker = CheckerService(self.settings)
        self.connectivity = ConnectivityGuard(self.settings)
        self.scorer = ScorerService(self.settings)
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._reserved_ids: set[int] = set()

    async def start(self) -> None:
        """Start the shared HTTP client and checker worker tasks."""
        if self._running:
            return
        self._running = True
        await self.connectivity.start()
        await self.checker.start()
        worker_count = self.settings.checker_concurrency
        self._workers = [
            asyncio.create_task(self._worker(index), name=f"checker-worker-{index}")
            for index in range(worker_count)
        ]
        logger.info("Checker workers started: %s", worker_count)

    async def stop(self) -> None:
        """Drain the queue, cancel workers, and release the HTTP client."""
        self._running = False
        drained = self._drain_queue()
        if drained:
            logger.info("Checker queue drained: %s pending checks skipped", drained)
        self._reserved_ids.clear()
        for worker in self._workers:
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        await self.checker.close()
        await self.connectivity.close()
        logger.info("Checker workers stopped")

    def _drain_queue(self) -> int:
        """Remove every pending queue item without running checks."""
        drained = 0
        while True:
            try:
                proxy_id = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if proxy_id is not None:
                self._reserved_ids.discard(proxy_id)
            drained += 1
            self.queue.task_done()
        return drained

    async def offer_proxies(self, proxy_ids: list[int]) -> int:
        """Try to enqueue each proxy id; skip duplicates and full queue."""
        added = 0
        for proxy_id in proxy_ids:
            if self._offer_proxy(proxy_id):
                added += 1
        return added

    def _offer_proxy(self, proxy_id: int) -> bool:
        """Enqueue one proxy if it is not reserved and the queue has space."""
        if proxy_id in self._reserved_ids:
            return False
        try:
            self.queue.put_nowait(proxy_id)
        except asyncio.QueueFull:
            return False
        self._reserved_ids.add(proxy_id)
        return True

    async def refill_queue(self) -> int:
        """Load pending proxies from the DB and fill free queue slots."""
        slots = self.settings.checker_queue_max_size - self.queue.qsize()
        if slots <= 0:
            return 0

        batch = min(slots, self.settings.checker_enqueue_batch_size)
        exclude = frozenset(self._reserved_ids)

        def _load_ids() -> tuple[list[int], int, int, str]:
            db = SessionLocal()
            try:
                self._recover_stuck_checking(db)
                ids, last_checked = self._fetch_queue_batch_ids(db, batch, exclude)
                pending, healthy_due = self._count_queue_candidates(db, exclude)
                return ids, pending, healthy_due, last_checked
            finally:
                db.close()

        proxy_ids, pending, healthy_due, last_checked = await asyncio.to_thread(_load_ids)
        added = await self.offer_proxies(proxy_ids)

        if added:
            logger.info(
                "Checker queue refilled added=%s queue=%s pending=%s healthy_due=%s last_checked=%s",
                added,
                self.queue.qsize(),
                pending,
                healthy_due,
                last_checked,
            )
        elif pending and self.queue.qsize() == 0:
            logger.info(
                "Checker queue empty with %s pending proxies waiting for slots",
                pending,
            )

        return added

    def _count_queue_candidates(
        self,
        db: Session,
        exclude_ids: frozenset[int],
    ) -> tuple[int, int]:
        """Count proxies eligible for the checker queue and due HEALTHY rechecks."""
        now = utc_now()
        recheck_due_cutoff = now - timedelta(seconds=self.settings.recheck_interval)

        healthy_query = db.query(func.count(Proxy.id)).filter(
            Proxy.status == ProxyStatus.HEALTHY,
            (Proxy.cooldown_until.is_(None)) | (Proxy.cooldown_until <= now),
            (Proxy.last_checked.is_(None)) | (Proxy.last_checked <= recheck_due_cutoff),
        )
        if exclude_ids:
            healthy_query = healthy_query.filter(~Proxy.id.in_(exclude_ids))
        healthy_due = int(healthy_query.scalar() or 0)

        pending_query = db.query(func.count(Proxy.id)).filter(
            Proxy.status.in_(
                [ProxyStatus.NEW, ProxyStatus.DEGRADED, ProxyStatus.DEAD]
            ),
            (Proxy.cooldown_until.is_(None)) | (Proxy.cooldown_until <= now),
        )
        if exclude_ids:
            pending_query = pending_query.filter(~Proxy.id.in_(exclude_ids))
        pending = int(pending_query.scalar() or 0)

        return pending + healthy_due, healthy_due

    def _fetch_queue_batch_ids(
        self,
        db: Session,
        limit: int,
        exclude_ids: frozenset[int],
    ) -> tuple[list[int], str]:
        """Pick queue batch with equal-ish slots per status tier."""
        now = utc_now()
        recheck_due_cutoff = now - timedelta(seconds=self.settings.recheck_interval)
        seen = set(exclude_ids)
        slots = self._allocate_state_slots(limit, len(QUEUE_STATE_ORDER))

        def filter_seen(query):
            if seen:
                return query.filter(~Proxy.id.in_(seen))
            return query

        def healthy_query():
            return filter_seen(
                db.query(Proxy).filter(
                    Proxy.status == ProxyStatus.HEALTHY,
                    (Proxy.cooldown_until.is_(None)) | (Proxy.cooldown_until <= now),
                    (Proxy.last_checked.is_(None)) | (Proxy.last_checked <= recheck_due_cutoff),
                )
            )

        def status_query(statuses: list[ProxyStatus], *, cooldown_only: bool = False):
            query = db.query(Proxy).filter(Proxy.status.in_(statuses))
            if cooldown_only:
                query = query.filter(
                    (Proxy.cooldown_until.is_(None)) | (Proxy.cooldown_until <= now)
                )
            return filter_seen(query)

        query_builders = [
            healthy_query,
            lambda: status_query([ProxyStatus.NEW]),
            lambda: status_query([ProxyStatus.DEGRADED]),
            lambda: status_query([ProxyStatus.DEAD], cooldown_only=True),
        ]

        pools: dict[str, list[int]] = {}
        selected_rows: list[tuple[int, datetime | None]] = []
        for key, slot, build_query in zip(QUEUE_STATE_ORDER, slots, query_builders):
            picked = self._pick_fair_proxy_rows(db, build_query(), slot)
            pool_ids = []
            for proxy_id, last_checked in picked:
                pool_ids.append(proxy_id)
                selected_rows.append((proxy_id, last_checked))
                seen.add(proxy_id)
            pools[key] = pool_ids

        shortfall = limit - sum(len(pool) for pool in pools.values())
        if shortfall > 0:
            for key, build_query in zip(QUEUE_STATE_ORDER, query_builders):
                if shortfall <= 0:
                    break
                extra = self._pick_fair_proxy_rows(db, build_query(), shortfall)
                extra_ids = []
                for proxy_id, last_checked in extra:
                    extra_ids.append(proxy_id)
                    selected_rows.append((proxy_id, last_checked))
                    seen.add(proxy_id)
                pools[key].extend(extra_ids)
                shortfall -= len(extra_ids)

        collected = self._round_robin_state_pools(pools, limit)
        return collected, self._format_last_checked_range(selected_rows)

    @staticmethod
    def _allocate_state_slots(limit: int, state_count: int) -> list[int]:
        """Split a batch limit into nearly equal per-status quotas."""
        if limit <= 0 or state_count <= 0:
            return []
        base, remainder = divmod(limit, state_count)
        return [base + (1 if index < remainder else 0) for index in range(state_count)]

    @staticmethod
    def _round_robin_state_pools(pools: dict[str, list[int]], limit: int) -> list[int]:
        """Interleave proxy ids across status tiers for queue ordering."""
        pointers = dict.fromkeys(QUEUE_STATE_ORDER, 0)
        collected: list[int] = []
        while len(collected) < limit:
            progress = False
            for key in QUEUE_STATE_ORDER:
                if len(collected) >= limit:
                    break
                pool = pools.get(key, [])
                pointer = pointers[key]
                if pointer < len(pool):
                    collected.append(pool[pointer])
                    pointers[key] = pointer + 1
                    progress = True
            if not progress:
                break
        return collected

    @staticmethod
    def _enabled_source_ids(db: Session) -> list[int]:
        """Return enabled provider ids in stable priority order."""
        rows = (
            db.query(ProxySource.id)
            .filter(ProxySource.enabled.is_(True))
            .order_by(ProxySource.priority.desc(), ProxySource.name.asc())
            .all()
        )
        return [row[0] for row in rows]

    @staticmethod
    def _round_robin_proxy_rows(
        buckets: dict[int, list[tuple[int, datetime | None]]],
        limit: int,
    ) -> list[tuple[int, datetime | None]]:
        """Interleave proxy candidates across provider buckets without duplicates."""
        if limit <= 0 or not buckets:
            return []

        order = list(buckets.keys())
        random.shuffle(order)
        pointers = dict.fromkeys(order, 0)
        selected: list[tuple[int, datetime | None]] = []
        seen: set[int] = set()

        while len(selected) < limit and order:
            round_progress = False
            exhausted: list[int] = []
            for source_id in order:
                if len(selected) >= limit:
                    break

                pool = buckets[source_id]
                pointer = pointers[source_id]
                while pointer < len(pool):
                    proxy_id, last_checked = pool[pointer]
                    pointer += 1
                    if proxy_id in seen:
                        continue
                    seen.add(proxy_id)
                    selected.append((proxy_id, last_checked))
                    pointers[source_id] = pointer
                    round_progress = True
                    break
                else:
                    pointers[source_id] = pointer
                    exhausted.append(source_id)

            for source_id in exhausted:
                order.remove(source_id)
            if not round_progress:
                break

        return selected

    def _pick_fair_proxy_rows(
        self,
        db: Session,
        query,
        limit: int,
    ) -> list[tuple[int, datetime | None]]:
        """Pick proxies with round-robin fairness across enabled providers."""
        if limit <= 0:
            return []

        pool_size = max(limit, self.settings.checker_selection_pool_size)
        source_ids = self._enabled_source_ids(db)
        bucket_count = max(len(source_ids) + 1, 1)
        per_source_pool = max(1, pool_size // bucket_count)

        buckets: dict[int, list[tuple[int, datetime | None]]] = {}
        for source_id in source_ids:
            scoped = query.join(ProxySourceLink, ProxySourceLink.proxy_id == Proxy.id).filter(
                ProxySourceLink.source_id == source_id
            )
            rows = (
                scoped.with_entities(Proxy.id, Proxy.last_checked)
                .order_by(Proxy.last_checked.asc().nullsfirst(), Proxy.id.asc())
                .limit(per_source_pool)
                .all()
            )
            if rows:
                shuffled = list(rows)
                random.shuffle(shuffled)
                buckets[source_id] = shuffled

        linked_ids = db.query(ProxySourceLink.proxy_id).distinct().scalar_subquery()
        unlinked_rows = (
            query.filter(~Proxy.id.in_(linked_ids))
            .with_entities(Proxy.id, Proxy.last_checked)
            .order_by(Proxy.last_checked.asc().nullsfirst(), Proxy.id.asc())
            .limit(per_source_pool)
            .all()
        )
        if unlinked_rows:
            shuffled = list(unlinked_rows)
            random.shuffle(shuffled)
            buckets[0] = shuffled

        if not buckets:
            return []

        return self._round_robin_proxy_rows(buckets, limit)

    @staticmethod
    def _format_last_checked_range(
        rows: list[tuple[int, datetime | None]],
    ) -> str:
        """Format last_checked timestamps for refill logs (24h, UTC)."""
        if not rows:
            return "n/a"

        times = [last_checked for _, last_checked in rows if last_checked is not None]
        if not times:
            return "never"

        oldest = min(times)
        newest = max(times)
        if oldest == newest:
            return format_log_datetime(oldest)
        return f"{format_log_datetime(oldest)} .. {format_log_datetime(newest)}"

    def _recover_stuck_checking(self, db: Session) -> list[int]:
        """Move proxies stuck in CHECKING back to DEGRADED after a timeout window."""
        cutoff = utc_now() - timedelta(seconds=self.settings.check_timeout * 3)
        rows = (
            db.query(Proxy.id)
            .filter(
                Proxy.status == ProxyStatus.CHECKING,
                Proxy.updated_at < cutoff,
            )
            .all()
        )
        stuck_ids = [row[0] for row in rows]
        if not stuck_ids:
            return []

        db.query(Proxy).filter(Proxy.id.in_(stuck_ids)).update(
            {Proxy.status: ProxyStatus.DEGRADED},
            synchronize_session=False,
        )
        db.commit()
        logger.warning("Recovered %s proxies stuck in CHECKING", len(stuck_ids))
        return stuck_ids

    async def _worker(self, worker_id: int) -> None:
        """Consume proxy ids from the queue until cancelled or poison pill received."""
        while True:
            proxy_id = await self.queue.get()
            try:
                if proxy_id is None:
                    break
                await self._check_proxy(proxy_id)
            except Exception:
                logger.exception("Checker worker %s failed for proxy_id=%s", worker_id, proxy_id)
            finally:
                if proxy_id is not None:
                    self._reserved_ids.discard(proxy_id)
                self.queue.task_done()

    async def _check_proxy(self, proxy_id: int) -> None:
        """Mark proxy as CHECKING, run HTTP probe, persist outcome and score."""
        if not await self.connectivity.is_available():
            logger.debug("Skipping proxy_id=%s check — no direct internet connectivity", proxy_id)
            return

        target = await asyncio.to_thread(self._mark_checking, proxy_id)
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

        if not result.success and not await self.connectivity.is_available():
            await asyncio.to_thread(self._revert_check, target)
            logger.warning(
                "[%s] Proxy %s check discarded — connectivity lost during probe",
                target.source_label,
                target.url,
            )
            return

        await asyncio.to_thread(self._persist_result, target, result)

    def _revert_check(self, target: ProxyCheckTarget) -> None:
        """Restore previous status when a failed probe is inconclusive (no internet)."""
        db = SessionLocal()
        try:
            proxy = db.query(Proxy).filter(Proxy.id == target.proxy_id).one_or_none()
            if proxy is None:
                return
            proxy.status = ProxyStatus(target.previous_status)
            db.commit()
        finally:
            db.close()

    def _mark_checking(self, proxy_id: int) -> ProxyCheckTarget | None:
        """Transition proxy to CHECKING and return data needed for the HTTP probe."""
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
        """Apply check outcome, recalculate score, and emit structured logs."""
        db = SessionLocal()
        try:
            proxy = db.query(Proxy).filter(Proxy.id == target.proxy_id).one_or_none()
            if proxy is None:
                return

            previous_status = target.previous_status
            removed = self._apply_result(db, proxy, result)
            if removed:
                db.commit()
                logger.info(
                    "[%s] Proxy %s removed after %s consecutive DEAD marks",
                    target.source_label,
                    target.url,
                    self.settings.dead_mark_removal_threshold,
                )
                return

            source_count = self._count_sources(db, proxy.id)
            self.scorer.apply_to_proxy(proxy, source_count=source_count)
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
        """Return comma-separated source names for log context."""
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

    @staticmethod
    def _count_sources(db: Session, proxy_id: int) -> int:
        """Count linked sources; minimum 1 for scorer multi-source bonus math."""
        count = (
            db.query(func.count(ProxySourceLink.id))
            .filter(ProxySourceLink.proxy_id == proxy_id)
            .scalar()
            or 0
        )
        return max(count, 1)

    def _remove_proxy(self, db: Session, proxy: Proxy) -> None:
        """Delete source links and the proxy row."""
        db.query(ProxySourceLink).filter(ProxySourceLink.proxy_id == proxy.id).delete(
            synchronize_session=False
        )
        db.delete(proxy)

    def _apply_result(self, db: Session, proxy: Proxy, result: CheckResult) -> bool:
        """Update proxy counters, status, cooldown; return True if proxy was removed."""
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
            proxy.last_error = result.error or "proxy authentication required"
            return False

        if result.success:
            proxy.success_count += 1
            proxy.consecutive_failures = 0
            proxy.consecutive_dead_marks = 0
            proxy.cooldown_until = None
            proxy.cooldown_level = 0
            proxy.last_success = now
            proxy.last_error = None
            proxy.status = ProxyStatus.HEALTHY
            return False

        proxy.failure_count += 1
        proxy.consecutive_failures += 1
        proxy.last_failure = now
        proxy.last_error = result.error

        if proxy.consecutive_failures >= self.settings.failure_threshold:
            proxy.consecutive_dead_marks += 1
            if proxy.consecutive_dead_marks >= self.settings.dead_mark_removal_threshold:
                self._remove_proxy(db, proxy)
                return True

            proxy.status = ProxyStatus.DEAD
            proxy.was_dead = True
            proxy.cooldown_level = min(proxy.cooldown_level + 1, self.settings.cooldown_max_level)
            cooldown_seconds = min(
                self.settings.cooldown_initial * (2 ** (proxy.cooldown_level - 1)),
                self.settings.cooldown_max,
            )
            proxy.cooldown_until = now + timedelta(seconds=cooldown_seconds)
        else:
            proxy.status = ProxyStatus.DEGRADED

        return False
