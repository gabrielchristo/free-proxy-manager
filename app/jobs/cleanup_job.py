import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Proxy, ProxyStatus

logger = logging.getLogger(__name__)


class CleanupJob:
    """Removes dead proxies that never succeeded and were not seen recently."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def run(self, db: Session) -> int:
        """Delete stale DEAD proxies; returns number removed."""
        cutoff = datetime.now(UTC) - timedelta(days=self.settings.cleanup_stale_days)
        stale = (
            db.query(Proxy)
            .filter(
                Proxy.status == ProxyStatus.DEAD,
                Proxy.last_success.is_(None),
                Proxy.last_seen < cutoff,
            )
            .all()
        )
        removed = len(stale)
        for proxy in stale:
            db.delete(proxy)
        if removed:
            db.commit()
            logger.info("Cleanup removed %s stale proxies", removed)
        return removed
