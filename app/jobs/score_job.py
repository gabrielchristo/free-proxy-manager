import logging

from sqlalchemy.orm import Session

from app.models import Proxy
from app.services.scorer import ScorerService

logger = logging.getLogger(__name__)


class ScoreJob:
    def __init__(self, scorer: ScorerService | None = None) -> None:
        self.scorer = scorer or ScorerService()

    def run(self, db: Session) -> int:
        updated = 0
        for proxy in db.query(Proxy).all():
            self.scorer.apply_to_proxy(proxy)
            updated += 1
        db.commit()
        logger.info("Score recalculation completed for %s proxies", updated)
        return updated
