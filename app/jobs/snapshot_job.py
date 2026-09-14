import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import PoolSnapshot, Proxy
from app.services.pool import PoolService

logger = logging.getLogger(__name__)


class SnapshotJob:
    """Persists periodic pool status counts for historical charts."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.pool_service = PoolService(self.settings)

    def run(self, db: Session) -> None:
        """Record current pool counts and prune snapshots older than retention."""
        pool = self.pool_service.get_pool_stats(db)
        total = db.query(func.count(Proxy.id)).scalar() or 0
        snapshot = PoolSnapshot(
            recorded_at=datetime.now(UTC),
            total_proxies=total,
            healthy=pool.healthy,
            degraded=pool.degraded,
            dead=pool.dead,
            new=pool.new,
            checking=pool.checking,
            disabled=pool.disabled,
            in_cooldown=pool.in_cooldown,
        )
        db.add(snapshot)
        db.commit()

        cutoff = datetime.now(UTC) - timedelta(days=self.settings.stats_snapshot_retention_days)
        removed = (
            db.query(PoolSnapshot)
            .filter(PoolSnapshot.recorded_at < cutoff)
            .delete(synchronize_session=False)
        )
        if removed:
            db.commit()
            logger.info("Snapshot retention removed %s old rows", removed)
