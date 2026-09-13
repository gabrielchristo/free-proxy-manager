from app.config import Settings, get_settings
from app.datetime_utils import as_utc, utc_now
from app.models import Proxy


class ScorerService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def calculate(self, proxy: Proxy) -> float:
        total_checks = proxy.success_count + proxy.failure_count
        success_rate = proxy.success_count / total_checks if total_checks else 0.0

        latency_score = 0.0
        if proxy.latency_ms is not None:
            latency_score = max(
                0.0,
                self.settings.scorer_latency_max
                - (proxy.latency_ms / self.settings.scorer_latency_divisor),
            )

        recency_score = 0.0
        if proxy.last_success is not None:
            age_hours = (utc_now() - as_utc(proxy.last_success)).total_seconds() / 3600
            recency_score = max(0.0, self.settings.scorer_recency_max - age_hours)

        stability_penalty = proxy.consecutive_failures * self.settings.scorer_failure_penalty
        history_bonus = min(proxy.success_count, self.settings.scorer_history_cap)
        protocol_bonus = (
            self.settings.scorer_https_bonus
            if proxy.protocol == self.settings.scorer_https_protocol
            else 0.0
        )

        score = (
            success_rate * self.settings.scorer_success_weight
            + latency_score
            + recency_score
            + history_bonus
            + protocol_bonus
            - stability_penalty
        )
        return round(max(0.0, min(self.settings.scorer_score_max, score)), 2)

    def apply_to_proxy(self, proxy: Proxy) -> float:
        proxy.score = self.calculate(proxy)
        return proxy.score
