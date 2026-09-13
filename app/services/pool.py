import logging
import random
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Proxy, ProxySource, ProxySourceLink, ProxyStatus
from app.schemas.proxy import (
    ProxyListItem,
    ProxyPoolStats,
    ProxyResponse,
    SourceStats,
    StatsResponse,
)

logger = logging.getLogger(__name__)

USABLE_STATUSES = {ProxyStatus.HEALTHY, ProxyStatus.DEGRADED}


class PoolService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _base_query(self, db: Session):
        now = datetime.now(UTC)
        return db.query(Proxy).filter(
            Proxy.status.in_(USABLE_STATUSES),
            (Proxy.cooldown_until.is_(None)) | (Proxy.cooldown_until <= now),
        )

    def get_best_proxy(
        self,
        db: Session,
        *,
        protocol: str | None = None,
        country: str | None = None,
        country_code: str | None = None,
        max_latency: float | None = None,
        anonymous: bool | None = None,
        min_score: float | None = None,
    ) -> Proxy | None:
        query = self._base_query(db)
        query = self._apply_filters(
            query,
            protocol=protocol,
            country=country,
            country_code=country_code,
            max_latency=max_latency,
            anonymous=anonymous,
            min_score=min_score or self.settings.pool_min_score,
        )

        candidates = (
            query.order_by(Proxy.score.desc(), Proxy.latency_ms.asc())
            .limit(self.settings.pool_top_candidates)
            .all()
        )
        if not candidates:
            return None

        weights = [
            max(proxy.score, self.settings.pool_selection_min_weight) for proxy in candidates
        ]
        return random.choices(candidates, weights=weights, k=1)[0]

    def list_proxies(
        self,
        db: Session,
        *,
        limit: int | None = None,
        offset: int = 0,
        protocol: str | None = None,
        country: str | None = None,
        country_code: str | None = None,
        status: str | None = None,
        max_latency: float | None = None,
        anonymous: bool | None = None,
        min_score: float | None = None,
    ) -> tuple[int, list[ProxyListItem]]:
        page_limit = limit or self.settings.api_default_limit
        query = db.query(Proxy)
        if status:
            query = query.filter(Proxy.status == ProxyStatus(status))
        else:
            query = self._base_query(db)

        query = self._apply_filters(
            query,
            protocol=protocol,
            country=country,
            country_code=country_code,
            max_latency=max_latency,
            anonymous=anonymous,
            min_score=min_score,
        )

        total = query.count()
        rows = (
            query.order_by(Proxy.score.desc(), Proxy.latency_ms.asc())
            .offset(offset)
            .limit(page_limit)
            .all()
        )
        return total, [self._to_list_item(proxy) for proxy in rows]

    def get_stats(self, db: Session) -> StatsResponse:
        now = datetime.now(UTC)
        total = db.query(func.count(Proxy.id)).scalar() or 0

        def count_status(status: ProxyStatus) -> int:
            return db.query(func.count(Proxy.id)).filter(Proxy.status == status).scalar() or 0

        in_cooldown = (
            db.query(func.count(Proxy.id))
            .filter(Proxy.cooldown_until.isnot(None), Proxy.cooldown_until > now)
            .scalar()
            or 0
        )

        pool = ProxyPoolStats(
            healthy=count_status(ProxyStatus.HEALTHY),
            degraded=count_status(ProxyStatus.DEGRADED),
            dead=count_status(ProxyStatus.DEAD),
            new=count_status(ProxyStatus.NEW),
            checking=count_status(ProxyStatus.CHECKING),
            disabled=count_status(ProxyStatus.DISABLED),
            in_cooldown=in_cooldown,
        )

        http_count = db.query(func.count(Proxy.id)).filter(Proxy.protocol == "http").scalar() or 0
        https_count = (
            db.query(func.count(Proxy.id)).filter(Proxy.protocol == "https").scalar() or 0
        )

        avg_latency = (
            db.query(func.avg(Proxy.latency_ms))
            .filter(Proxy.latency_ms.isnot(None), Proxy.status.in_(USABLE_STATUSES))
            .scalar()
        )

        success_total = (
            db.query(func.sum(Proxy.success_count)).filter(Proxy.status.in_(USABLE_STATUSES)).scalar()
            or 0
        )
        failure_total = (
            db.query(func.sum(Proxy.failure_count)).filter(Proxy.status.in_(USABLE_STATUSES)).scalar()
            or 0
        )
        checks_total = success_total + failure_total
        success_rate = (success_total / checks_total * 100) if checks_total else None

        country_rows = (
            db.query(Proxy.country_code, func.count(Proxy.id))
            .filter(
                Proxy.country_code.isnot(None),
                Proxy.status.in_(USABLE_STATUSES),
            )
            .group_by(Proxy.country_code)
            .all()
        )
        proxies_by_country = {code: count for code, count in country_rows if code}

        sources = []
        for source in db.query(ProxySource).order_by(ProxySource.priority.desc()).all():
            valid_proxies = (
                db.query(func.count(Proxy.id))
                .join(ProxySourceLink, ProxySourceLink.proxy_id == Proxy.id)
                .filter(
                    ProxySourceLink.source_id == source.id,
                    Proxy.status.in_(USABLE_STATUSES),
                )
                .scalar()
                or 0
            )
            rate = (valid_proxies / source.proxies_found * 100) if source.proxies_found else None
            sources.append(
                SourceStats(
                    name=source.name,
                    enabled=source.enabled,
                    proxies_found=source.proxies_found,
                    valid_proxies=valid_proxies,
                    success_rate=round(rate, 2) if rate is not None else None,
                    last_run=source.last_run,
                    last_success=source.last_success,
                    last_error=source.last_error,
                )
            )

        return StatsResponse(
            total_proxies=total,
            pool=pool,
            http=http_count,
            https=https_count,
            average_latency=round(avg_latency, 2) if avg_latency is not None else None,
            success_rate=round(success_rate, 2) if success_rate is not None else None,
            proxies_by_country=proxies_by_country,
            sources=sources,
        )

    @staticmethod
    def to_response(proxy: Proxy) -> ProxyResponse:
        return ProxyResponse(
            proxy=proxy.url,
            protocol=proxy.protocol,
            host=proxy.host,
            port=proxy.port,
            latency_ms=proxy.latency_ms,
            score=proxy.score,
            country=proxy.country,
            country_code=proxy.country_code,
            city=proxy.city,
            anonymity=proxy.anonymity,
            isp=proxy.isp,
            asn=proxy.asn,
            org=proxy.org,
            ssl=proxy.ssl,
            source_latency_ms=proxy.source_latency_ms,
            source_uptime_percent=proxy.source_uptime_percent,
            source_speed=proxy.source_speed,
            source_last_checked=proxy.source_last_checked,
            last_error=proxy.last_error,
            metadata=proxy.metadata_json,
            status=proxy.status.value,
        )

    @staticmethod
    def _to_list_item(proxy: Proxy) -> ProxyListItem:
        return ProxyListItem(
            id=proxy.id,
            proxy=proxy.url,
            protocol=proxy.protocol,
            host=proxy.host,
            port=proxy.port,
            country=proxy.country,
            country_code=proxy.country_code,
            city=proxy.city,
            anonymity=proxy.anonymity,
            isp=proxy.isp,
            asn=proxy.asn,
            org=proxy.org,
            ssl=proxy.ssl,
            source_latency_ms=proxy.source_latency_ms,
            source_uptime_percent=proxy.source_uptime_percent,
            source_speed=proxy.source_speed,
            source_last_checked=proxy.source_last_checked,
            last_error=proxy.last_error,
            metadata=proxy.metadata_json,
            status=proxy.status.value,
            latency_ms=proxy.latency_ms,
            score=proxy.score,
            success_count=proxy.success_count,
            failure_count=proxy.failure_count,
            last_checked=proxy.last_checked,
        )

    def _apply_filters(
        self,
        query,
        *,
        protocol: str | None,
        country: str | None,
        country_code: str | None,
        max_latency: float | None,
        anonymous: bool | None,
        min_score: float | None,
    ):
        if protocol:
            query = query.filter(Proxy.protocol == protocol.lower())
        if country:
            query = query.filter(Proxy.country.ilike(f"%{country}%"))
        if country_code:
            query = query.filter(Proxy.country_code == country_code.upper())
        if max_latency is not None:
            query = query.filter(Proxy.latency_ms.isnot(None), Proxy.latency_ms <= max_latency)
        if anonymous is True:
            query = query.filter(
                Proxy.anonymity.isnot(None),
                Proxy.anonymity != self.settings.anonymous_exclude_value,
            )
        if min_score is not None:
            query = query.filter(Proxy.score >= min_score)
        return query
