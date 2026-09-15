from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

DEFAULT_MANAGER_URL = "http://localhost:9321"
DEFAULT_TARGET_URL = "http://detectportal.firefox.com/success.txt"
DEFAULT_TIMEOUT = 20.0
PROXY_CALLS = 10
LIST_PROXY_COUNT = 10

HISTORY_MONTH_DAYS = 30
HISTORY_MONTH_HOURS = HISTORY_MONTH_DAYS * 24
DEFAULT_SNAPSHOT_INTERVAL = 300
HISTORY_MONTH_MAX_POINTS = HISTORY_MONTH_HOURS * 3600 // DEFAULT_SNAPSHOT_INTERVAL
HISTORY_AUTO_REFRESH_SECONDS = 60
OVERVIEW_AUTO_REFRESH_SECONDS = 60

ANONYMITY_RANK = {
    "elite": 3,
    "high_anonymous": 3,
    "anonymous": 2,
    "transparent": 1,
}


@dataclass(slots=True)
class PoolDiagnostics:
    health_status: str | None = None
    pool_healthy: int = 0
    pool_degraded: int = 0
    pool_new: int = 0
    pool_checking: int = 0
    pool_dead: int = 0
    total_proxies: int = 0
    list_filter_total: int = 0
    list_filter_description: str = ""
    fetch_error: str | None = None


@dataclass(slots=True)
class ProxySnapshot:
    proxy_url: str
    protocol: str
    host: str
    port: int
    score: float | None = None
    status: str | None = None
    anonymity: str | None = None
    country: str | None = None
    country_code: str | None = None
    city: str | None = None
    latency_ms: float | None = None
    success_count: int | None = None
    failure_count: int | None = None
    last_checked: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TestResult:
    index: int
    source: str
    source_call: int
    proxy: ProxySnapshot | None
    fetch_ok: bool
    fetch_error: str | None
    test_ok: bool
    test_error: str | None
    http_status: int | None
    response_time_ms: float | None
    tested_at: str
    skipped: bool = False


@dataclass(slots=True)
class PoolHistoryPoint:
    recorded_at: datetime
    total_proxies: int
    healthy: int
    degraded: int
    dead: int
    new: int
    checking: int
    disabled: int
    in_cooldown: int


def iso_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value)


def anonymity_rank(level: str | None) -> int:
    if not level:
        return 0
    return ANONYMITY_RANK.get(level.strip().lower(), 0)


def snapshot_from_api(payload: dict[str, Any]) -> ProxySnapshot:
    return ProxySnapshot(
        proxy_url=payload["proxy"],
        protocol=payload["protocol"],
        host=payload["host"],
        port=payload["port"],
        score=payload.get("score"),
        status=payload.get("status"),
        anonymity=payload.get("anonymity"),
        country=payload.get("country"),
        country_code=payload.get("country_code"),
        city=payload.get("city"),
        latency_ms=payload.get("latency_ms"),
        success_count=payload.get("success_count"),
        failure_count=payload.get("failure_count"),
        last_checked=iso_value(payload.get("last_checked")),
        raw=payload,
    )
