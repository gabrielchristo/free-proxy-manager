import pytest

from app.services.checker import CheckerService
from app.services.scorer import ScorerService
from app.models import Proxy, ProxyStatus


def test_checker_allowlist_accepts_google():
    checker = CheckerService()
    assert checker.validate_check_url("https://www.google.com/") == "https://www.google.com/"


def test_checker_allowlist_rejects_other_hosts():
    checker = CheckerService()
    with pytest.raises(ValueError):
        checker.validate_check_url("https://example.com/")


def test_scorer_prefers_stable_low_latency_proxy():
    scorer = ScorerService()
    stable = Proxy(
        host="1.1.1.1",
        port=8080,
        protocol="http",
        status=ProxyStatus.HEALTHY,
        success_count=20,
        failure_count=2,
        consecutive_failures=0,
        latency_ms=120,
    )
    unstable = Proxy(
        host="2.2.2.2",
        port=8080,
        protocol="http",
        status=ProxyStatus.DEAD,
        success_count=2,
        failure_count=10,
        consecutive_failures=4,
        latency_ms=900,
    )

    assert scorer.calculate(stable) > scorer.calculate(unstable)
