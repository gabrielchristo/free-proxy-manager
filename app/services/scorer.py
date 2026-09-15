from app.config import Settings, get_settings
from app.datetime_utils import as_utc, utc_now
from app.models import Proxy


class ScorerService:
    """Calculates a 0–100 score from proxy health metrics and metadata bonuses."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def calculate(self, proxy: Proxy, source_count: int = 1) -> float:
        """Return the weighted score for one proxy without mutating it."""
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
        multi_source_bonus = 0.0
        if source_count > 1:
            multi_source_bonus = min(
                (source_count - 1) * self.settings.scorer_multi_source_bonus,
                self.settings.scorer_multi_source_cap,
            )
        anonymity_bonus = self._anonymity_bonus(proxy)

        score = (
            success_rate * self.settings.scorer_success_weight
            + latency_score
            + recency_score
            + history_bonus
            + protocol_bonus
            + multi_source_bonus
            + anonymity_bonus
            - stability_penalty
        )
        return round(max(0.0, min(self.settings.scorer_score_max, score)), 2)

    def apply_to_proxy(self, proxy: Proxy, source_count: int = 1) -> float:
        """Calculate and persist the score on the proxy instance."""
        proxy.score = self.calculate(proxy, source_count=source_count)
        return proxy.score

    def _anonymity_bonus(self, proxy: Proxy) -> float:
        """Map anonymity level to configured bonus points."""
        if not proxy.anonymity:
            return 0.0
        level = proxy.anonymity.strip().lower()
        return self.settings.scorer_anonymity_bonus.get(level, 0.0)
