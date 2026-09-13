import pytest
from datetime import datetime

from app.config import get_settings
from app.services.checker import CheckerService
from app.services.scorer import ScorerService
from app.models import Proxy, ProxyStatus


def test_checker_allowlist_accepts_configured_url():
    settings = get_settings()
    checker = CheckerService(settings)
    assert checker.validate_check_url(settings.check_url) == settings.check_url


def test_checker_allowlist_rejects_other_hosts():
    checker = CheckerService(get_settings())
    with pytest.raises(ValueError):
        checker.validate_check_url("https://example.com/")


def test_scorer_prefers_stable_low_latency_proxy():
    settings = get_settings()
    scorer = ScorerService(settings)
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


def test_scorer_prefers_https_over_http_with_same_metrics():
    settings = get_settings()
    scorer = ScorerService(settings)
    base_kwargs = {
        "host": "1.1.1.1",
        "port": 8080,
        "status": ProxyStatus.HEALTHY,
        "success_count": 10,
        "failure_count": 1,
        "consecutive_failures": 0,
        "latency_ms": 150,
    }
    http_proxy = Proxy(protocol="http", **base_kwargs)
    https_proxy = Proxy(protocol=settings.scorer_https_protocol, **base_kwargs)

    assert scorer.calculate(https_proxy) > scorer.calculate(http_proxy)


def test_scorer_handles_naive_last_success():
    settings = get_settings()
    scorer = ScorerService(settings)
    proxy = Proxy(
        host="1.1.1.1",
        port=8080,
        protocol="http",
        status=ProxyStatus.HEALTHY,
        success_count=5,
        failure_count=0,
        consecutive_failures=0,
        latency_ms=100,
        last_success=datetime(2026, 3, 22, 12, 0, 0),
    )

    assert scorer.calculate(proxy) >= 0


def test_scorer_adds_bonus_for_multiple_sources():
    settings = get_settings()
    scorer = ScorerService(settings)
    proxy = Proxy(
        host="1.1.1.1",
        port=8080,
        protocol="http",
        status=ProxyStatus.HEALTHY,
        success_count=10,
        failure_count=1,
        consecutive_failures=0,
        latency_ms=150,
    )

    single_source_score = scorer.calculate(proxy, source_count=1)
    multi_source_score = scorer.calculate(proxy, source_count=3)

    assert multi_source_score == single_source_score + (2 * settings.scorer_multi_source_bonus)


def test_scorer_prefers_higher_anonymity_levels():
    settings = get_settings()
    scorer = ScorerService(settings)
    base_kwargs = {
        "host": "1.1.1.1",
        "port": 8080,
        "protocol": "http",
        "status": ProxyStatus.HEALTHY,
        "success_count": 10,
        "failure_count": 1,
        "consecutive_failures": 0,
        "latency_ms": 150,
    }
    transparent = Proxy(anonymity="transparent", **base_kwargs)
    anonymous = Proxy(anonymity="anonymous", **base_kwargs)
    elite = Proxy(anonymity="elite", **base_kwargs)

    transparent_score = scorer.calculate(transparent)
    anonymous_score = scorer.calculate(anonymous)
    elite_score = scorer.calculate(elite)

    assert anonymous_score > transparent_score
    assert elite_score > anonymous_score
    assert elite_score - transparent_score == pytest.approx(
        settings.scorer_anonymity_bonus["elite"] - settings.scorer_anonymity_bonus["transparent"]
    )

