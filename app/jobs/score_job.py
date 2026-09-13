import logging

from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.models import Proxy
from app.services.scorer import ScorerService

logger = logging.getLogger(__name__)


class ScoreJob:
    """Recalculates proxy scores in bounded batches to limit memory use."""

    def __init__(self, scorer: ScorerService | None = None) -> None:
        self.scorer = scorer or ScorerService()
        self.settings = get_settings()

    def run(self, db: Session) -> int:
        """Walk all proxies by id and update scores; returns count updated."""
        batch_size = self.settings.score_batch_size
        updated = 0
        last_id = 0

        while True:
            batch = (
                db.query(Proxy)
                .options(joinedload(Proxy.sources))
                .filter(Proxy.id > last_id)
                .order_by(Proxy.id.asc())
                .limit(batch_size)
                .all()
            )
            if not batch:
                break

            for proxy in batch:
                source_count = max(len(proxy.sources), 1)
                self.scorer.apply_to_proxy(proxy, source_count=source_count)
                updated += 1
                last_id = proxy.id

            db.commit()
            db.expunge_all()

        return updated
