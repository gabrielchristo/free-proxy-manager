import asyncio
import logging

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.datetime_utils import as_utc, utc_now
from app.database import SessionLocal
from app.models import Proxy, ProxySource, ProxySourceLink, ProxyStatus
from app.services.collector_helpers import apply_collected_fields, build_source_metadata
from app.sources.base import CollectedProxy, ProxySourceBase
from app.sources.loader import load_sources

logger = logging.getLogger(__name__)


class CollectorService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.sources = load_sources(self.settings)

    async def collect_all(self) -> list[int]:
        """Collect from all enabled sources and return proxy IDs queued for checking."""
        queued_ids: list[int] = []

        for source in self.sources:
            db = SessionLocal()
            try:
                db_source = self._get_or_create_source(db, source)
                if not db_source.enabled:
                    logger.info("[%s] Source disabled in database, skipping", source.name)
                    continue
                db_source.last_run = utc_now()
                db.commit()
            finally:
                db.close()

            logger.info("[%s] Collection started url=%s", source.name, source.url)
            try:
                collected = await source.collect()
                new_ids = await asyncio.to_thread(
                    self.persist_collected_for_source,
                    source.name,
                    source.url,
                    source.priority,
                    collected,
                )
                queued_ids.extend(new_ids)
                logger.info(
                    "[%s] Collection completed proxies=%s queued=%s",
                    source.name,
                    len(collected),
                    len(new_ids),
                )
            except Exception as exc:
                self._record_source_error(source.name, str(exc))
                logger.exception("[%s] Collection failed", source.name)

        return queued_ids

    def persist_collected_for_source(
        self,
        source_name: str,
        source_url: str,
        source_priority: int,
        collected: list[CollectedProxy],
    ) -> list[int]:
        db = SessionLocal()
        try:
            db_source = (
                db.query(ProxySource).filter(ProxySource.name == source_name).one_or_none()
            )
            if db_source is None:
                db_source = ProxySource(
                    name=source_name,
                    url=source_url,
                    enabled=True,
                    priority=source_priority,
                )
                db.add(db_source)
                db.flush()
            else:
                db_source.url = source_url
                db_source.priority = source_priority

            queued_ids = self._persist_collected(
                db,
                db_source.id,
                db_source.name,
                collected,
            )
            db_source.last_success = utc_now()
            db_source.last_error = None
            db_source.proxies_found = len(collected)
            db.commit()
            return queued_ids
        finally:
            db.close()

    def _record_source_error(self, source_name: str, error: str) -> None:
        db = SessionLocal()
        try:
            db_source = (
                db.query(ProxySource).filter(ProxySource.name == source_name).one_or_none()
            )
            if db_source is None:
                return
            db_source.last_error = error
            db.commit()
        finally:
            db.close()

    def _get_or_create_source(self, db: Session, source: ProxySourceBase) -> ProxySource:
        db_source = db.query(ProxySource).filter(ProxySource.name == source.name).one_or_none()
        if db_source is None:
            db_source = ProxySource(
                name=source.name,
                url=source.url,
                enabled=True,
                priority=source.priority,
            )
            db.add(db_source)
            db.flush()
        else:
            db_source.url = source.url
            db_source.priority = source.priority
        return db_source

    def _persist_collected(
        self,
        db: Session,
        source_id: int,
        source_name: str,
        collected: list[CollectedProxy],
    ) -> list[int]:
        now = utc_now()
        queued_ids: list[int] = []
        seen: set[tuple[str, str, int]] = set()
        batch_size = self.settings.collector_persist_batch_size
        since_commit = 0

        for item in collected:
            key = (item.protocol, item.host, item.port)
            if key in seen:
                continue
            seen.add(key)

            proxy = (
                db.query(Proxy)
                .filter(
                    Proxy.protocol == item.protocol,
                    Proxy.host == item.host,
                    Proxy.port == item.port,
                )
                .one_or_none()
            )

            is_new = proxy is None
            if proxy is None:
                proxy = Proxy(
                    host=item.host,
                    port=item.port,
                    protocol=item.protocol,
                    status=ProxyStatus.NEW,
                )
                db.add(proxy)
                db.flush()
                logger.info(
                    "[%s] Discovered new proxy %s",
                    source_name,
                    proxy.url,
                )
            else:
                proxy.last_seen = now

            apply_collected_fields(proxy, item)

            link = (
                db.query(ProxySourceLink)
                .filter(
                    ProxySourceLink.proxy_id == proxy.id,
                    ProxySourceLink.source_id == source_id,
                )
                .one_or_none()
            )
            if link is None:
                link = ProxySourceLink(proxy_id=proxy.id, source_id=source_id)
                db.add(link)
            else:
                link.last_seen = now
            link.source_metadata = build_source_metadata(item)

            if is_new or proxy.status in {ProxyStatus.NEW, ProxyStatus.DEAD, ProxyStatus.DEGRADED}:
                if proxy.cooldown_until is None or as_utc(proxy.cooldown_until) <= now:
                    queued_ids.append(proxy.id)

            since_commit += 1
            if since_commit >= batch_size:
                db.commit()
                db.expunge_all()
                since_commit = 0

        if since_commit > 0:
            db.commit()
            db.expunge_all()

        return queued_ids
