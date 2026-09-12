from datetime import UTC, datetime

from app.config import Settings, get_settings
from app.models import Proxy


class ScorerService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def calculate(self, proxy: Proxy) -> float:
        total_checks = proxy.success_count + proxy.failure_count
        success_rate = proxy.success_count / total_checks if total_checks else 0.0

        latency_score = 0.0
        if proxy.latency_ms is not None:
            latency_score = max(0.0, 40.0 - (proxy.latency_ms / 50.0))

        recency_score = 0.0
        if proxy.last_success:
            age_hours = (datetime.now(UTC) - proxy.last_success).total_seconds() / 3600
            recency_score = max(0.0, 20.0 - age_hours)

        stability_penalty = proxy.consecutive_failures * 10.0
        history_bonus = min(proxy.success_count, 20)

        score = (
            success_rate * 40.0
            + latency_score
            + recency_score
            + history_bonus
            - stability_penalty
        )
        return round(max(0.0, min(100.0, score)), 2)

    def apply_to_proxy(self, proxy: Proxy) -> float:
        proxy.score = self.calculate(proxy)
        return proxy.score
