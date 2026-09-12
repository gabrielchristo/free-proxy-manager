import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Proxy, ProxySource, ProxySourceLink, ProxyStatus
from app.sources.base import CollectedProxy, ProxySourceBase
from app.sources.proxyscrape import ProxyScrapeSource

logger = logging.getLogger(__name__)


class CollectorService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.sources = self._build_sources()

    def _build_sources(self) -> list[ProxySourceBase]:
        sources: list[ProxySourceBase] = []
        if self.settings.proxyscrape_enabled:
            sources.append(
                ProxyScrapeSource(
                    url=self.settings.proxyscrape_url,
                    priority=self.settings.proxyscrape_priority,
                )
            )
        return sources

    async def collect_all(self, db: Session) -> list[int]:
        """Collect from all enabled sources and return proxy IDs queued for checking."""
        queued_ids: list[int] = []

        for source in self.sources:
            db_source = self._get_or_create_source(db, source)
            if not db_source.enabled:
                continue

            db_source.last_run = datetime.now(UTC)
            try:
                collected = await source.collect()
                db_source.last_success = datetime.now(UTC)
                db_source.last_error = None
                db_source.proxies_found = len(collected)
                new_ids = self._persist_collected(db, db_source, collected)
                queued_ids.extend(new_ids)
                logger.info(
                    "Source %s completed: %s proxies, %s new/updated for check",
                    source.name,
                    len(collected),
                    len(new_ids),
                )
            except Exception as exc:
                db_source.last_error = str(exc)
                logger.exception("Source %s failed", source.name)

        db.commit()
        return queued_ids

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
        db_source: ProxySource,
        collected: list[CollectedProxy],
    ) -> list[int]:
        now = datetime.now(UTC)
        queued_ids: list[int] = []
        seen: set[tuple[str, str, int]] = set()

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
                    country=item.country,
                    country_code=item.country_code,
                    anonymity=item.anonymity,
                    status=ProxyStatus.NEW,
                )
                db.add(proxy)
                db.flush()
            else:
                proxy.last_seen = now
                if item.country:
                    proxy.country = item.country
                if item.country_code:
                    proxy.country_code = item.country_code
                if item.anonymity:
                    proxy.anonymity = item.anonymity

            link = (
                db.query(ProxySourceLink)
                .filter(
                    ProxySourceLink.proxy_id == proxy.id,
                    ProxySourceLink.source_id == db_source.id,
                )
                .one_or_none()
            )
            if link is None:
                link = ProxySourceLink(proxy_id=proxy.id, source_id=db_source.id)
                db.add(link)
            else:
                link.last_seen = now

            if is_new or proxy.status in {ProxyStatus.NEW, ProxyStatus.DEAD, ProxyStatus.DEGRADED}:
                if proxy.cooldown_until is None or proxy.cooldown_until <= now:
                    queued_ids.append(proxy.id)

        return queued_ids
