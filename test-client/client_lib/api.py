from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from client_lib.models import (
    PoolDiagnostics,
    PoolHistoryPoint,
    ProxySnapshot,
    anonymity_rank,
    iso_value,
    snapshot_from_api,
)


def format_manager_error(
    exc: httpx.HTTPError,
    manager_url: str,
    *,
    path: str = "",
) -> str:
    target = f"{manager_url.rstrip('/')}{path}"
    if isinstance(exc, httpx.ConnectError):
        return (
            f"Cannot connect to {target}.\n\n"
            "Check that free-proxy-manager is running and the Manager URL is correct "
            "(default: http://localhost:9321)."
        )
    if isinstance(exc, httpx.TimeoutException):
        return f"Request to {target} timed out."
    return str(exc) or repr(exc)


async def fetch_pool_diagnostics(
    client: httpx.AsyncClient,
    manager_url: str,
    *,
    list_protocol: str,
    list_status: str,
    list_anonymous: bool,
) -> PoolDiagnostics:
    diagnostics = PoolDiagnostics(
        list_filter_description=(
            f"protocol={list_protocol} status={list_status} "
            f"anonymous={'true' if list_anonymous else 'false'}"
        ),
    )
    try:
        health = await client.get(f"{manager_url}/health")
        health.raise_for_status()
        health_payload = health.json()
        diagnostics.health_status = health_payload.get("status")
        pool = health_payload.get("proxy_pool") or {}
        diagnostics.pool_healthy = int(pool.get("healthy") or 0)
        diagnostics.pool_degraded = int(pool.get("degraded") or 0)
        diagnostics.pool_new = int(pool.get("new") or 0)
        diagnostics.pool_checking = int(pool.get("checking") or 0)
        diagnostics.pool_dead = int(pool.get("dead") or 0)
    except httpx.HTTPError as exc:
        diagnostics.fetch_error = f"/health: {exc}"

    try:
        stats = await client.get(f"{manager_url}/stats")
        stats.raise_for_status()
        diagnostics.total_proxies = int(stats.json().get("total_proxies") or 0)
    except httpx.HTTPError as exc:
        if diagnostics.fetch_error:
            diagnostics.fetch_error += f"; /stats: {exc}"
        else:
            diagnostics.fetch_error = f"/stats: {exc}"

    list_params: dict[str, str | int] = {
        "protocol": list_protocol,
        "status": list_status,
        "limit": 1,
        "offset": 0,
    }
    if list_anonymous:
        list_params["anonymous"] = "true"
    try:
        response = await client.get(f"{manager_url}/proxies", params=list_params)
        response.raise_for_status()
        diagnostics.list_filter_total = int(response.json().get("total") or 0)
    except httpx.HTTPError as exc:
        if diagnostics.fetch_error:
            diagnostics.fetch_error += f"; /proxies count: {exc}"
        else:
            diagnostics.fetch_error = f"/proxies count: {exc}"

    return diagnostics


async def fetch_health(
    client: httpx.AsyncClient,
    manager_url: str,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        response = await client.get(f"{manager_url}/health")
        response.raise_for_status()
        return response.json(), None
    except httpx.HTTPError as exc:
        return None, format_manager_error(exc, manager_url, path="/health")


async def fetch_stats(
    client: httpx.AsyncClient,
    manager_url: str,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        response = await client.get(f"{manager_url}/stats")
        response.raise_for_status()
        return response.json(), None
    except httpx.HTTPError as exc:
        return None, format_manager_error(exc, manager_url, path="/stats")


async def fetch_proxy_from_endpoint(
    client: httpx.AsyncClient,
    manager_url: str,
    *,
    min_score: float | None = None,
) -> tuple[ProxySnapshot | None, str | None]:
    params: dict[str, str | float] = {}
    if min_score is not None:
        params["min_score"] = min_score
    try:
        response = await client.get(f"{manager_url}/proxy", params=params or None)
        response.raise_for_status()
        return snapshot_from_api(response.json()), None
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip()
        return None, f"HTTP {exc.response.status_code}: {detail or exc.response.reason_phrase}"
    except httpx.HTTPError as exc:
        return None, str(exc)


async def fetch_list_proxies(
    client: httpx.AsyncClient,
    manager_url: str,
    *,
    pick_count: int,
    list_limit: int,
    list_protocol: str,
    list_status: str,
    list_anonymous: bool,
) -> tuple[list[ProxySnapshot], int, str | None]:
    params: dict[str, str | int] = {
        "protocol": list_protocol,
        "status": list_status,
        "limit": list_limit,
        "offset": 0,
    }
    if list_anonymous:
        params["anonymous"] = "true"
    try:
        response = await client.get(f"{manager_url}/proxies", params=params)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        return [], 0, format_manager_error(exc, manager_url, path="/proxies")

    total = int(payload.get("total") or 0)
    items = payload.get("items", [])
    ranked = sorted(
        items,
        key=lambda item: (-anonymity_rank(item.get("anonymity")), -(item.get("score") or 0)),
    )
    selected = [snapshot_from_api(item) for item in ranked[:pick_count]]
    return selected, total, None


async def fetch_proxies_page(
    client: httpx.AsyncClient,
    manager_url: str,
    *,
    limit: int,
    offset: int,
    protocol: str | None = None,
    status: str | None = None,
    country: str | None = None,
    country_code: str | None = None,
    max_latency: float | None = None,
    anonymous: bool | None = None,
    min_score: float | None = None,
) -> tuple[list[dict[str, Any]], int, str | None]:
    params: dict[str, str | int | float] = {
        "limit": limit,
        "offset": offset,
    }
    if protocol:
        params["protocol"] = protocol
    if status:
        params["status"] = status
    if country:
        params["country"] = country
    if country_code:
        params["country_code"] = country_code
    if max_latency is not None:
        params["max_latency"] = max_latency
    if anonymous is True:
        params["anonymous"] = "true"
    if min_score is not None:
        params["min_score"] = min_score

    try:
        response = await client.get(f"{manager_url}/proxies", params=params)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        return [], 0, format_manager_error(exc, manager_url, path="/proxies")

    items = payload.get("items", [])
    total = int(payload.get("total") or 0)
    return items, total, None


async def fetch_all_proxies(
    client: httpx.AsyncClient,
    manager_url: str,
    *,
    page_size: int = 100,
    on_progress: Callable[[int, int], None] | None = None,
    **filters: Any,
) -> tuple[list[dict[str, Any]], int, str | None]:
    page_size = max(1, min(page_size, 100))
    offset = 0
    all_items: list[dict[str, Any]] = []
    total = 0

    while True:
        items, total, error = await fetch_proxies_page(
            client,
            manager_url,
            limit=page_size,
            offset=offset,
            **filters,
        )
        if error:
            return all_items, total, error
        all_items.extend(items)
        if on_progress:
            on_progress(len(all_items), total)
        if not items or len(all_items) >= total:
            break
        offset += page_size

    return all_items, total, None


async def fetch_pool_history(
    client: httpx.AsyncClient,
    manager_url: str,
    *,
    hours: int,
    limit: int,
) -> tuple[list[PoolHistoryPoint], str | None]:
    try:
        response = await client.get(
            f"{manager_url}/stats/history",
            params={"hours": hours, "limit": limit},
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 422:
            try:
                detail = exc.response.json().get("detail", exc.response.text)
            except Exception:
                detail = exc.response.text
            return [], (
                "The manager rejected the history query (HTTP 422). "
                "Restart free-proxy-manager to load the 30-day API limits "
                f"(hours<={hours}, limit<={limit}). Server detail: {detail}"
            )
        return [], format_manager_error(exc, manager_url, path="/stats/history")
    except httpx.HTTPError as exc:
        return [], format_manager_error(exc, manager_url, path="/stats/history")

    points: list[PoolHistoryPoint] = []
    for item in payload.get("items", []):
        pool = item.get("pool") or {}
        recorded_at = item.get("recorded_at")
        if isinstance(recorded_at, str):
            parsed_at = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
        else:
            parsed_at = datetime.now(UTC)
        points.append(
            PoolHistoryPoint(
                recorded_at=parsed_at,
                total_proxies=int(item.get("total_proxies") or 0),
                healthy=int(pool.get("healthy") or 0),
                degraded=int(pool.get("degraded") or 0),
                dead=int(pool.get("dead") or 0),
                new=int(pool.get("new") or 0),
                checking=int(pool.get("checking") or 0),
                disabled=int(pool.get("disabled") or 0),
                in_cooldown=int(pool.get("in_cooldown") or 0),
            )
        )
    return points, None


async def test_proxy_against_target(
    proxy: ProxySnapshot,
    target_url: str,
    timeout: float,
) -> tuple[bool, str | None, int | None, float]:
    import time

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            proxy=proxy.proxy_url,
            timeout=timeout,
            follow_redirects=True,
            verify=True,
        ) as probe:
            response = await probe.get(target_url)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        if 200 <= response.status_code <= 399:
            return True, None, response.status_code, elapsed_ms
        return False, f"HTTP {response.status_code}", response.status_code, elapsed_ms
    except httpx.TimeoutException:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        return False, "timeout", None, elapsed_ms
    except httpx.HTTPError as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        return False, str(exc), None, elapsed_ms


def format_proxy_row(item: dict[str, Any]) -> list[str]:
    metadata = item.get("metadata")
    if metadata is None:
        metadata_text = ""
    elif isinstance(metadata, dict):
        import json

        metadata_text = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    else:
        metadata_text = str(metadata)

    return [
        str(item.get("id", "")),
        str(item.get("proxy", "")),
        str(item.get("protocol", "")),
        str(item.get("host", "")),
        str(item.get("port", "")),
        str(item.get("status", "")),
        str(item.get("score", "")),
        str(item.get("latency_ms", "")),
        str(item.get("country", "") or ""),
        str(item.get("country_code", "") or ""),
        str(item.get("city", "") or ""),
        str(item.get("anonymity", "") or ""),
        str(item.get("isp", "") or ""),
        str(item.get("asn", "") or ""),
        str(item.get("org", "") or ""),
        str(item.get("ssl", "")),
        str(item.get("source_latency_ms", "")),
        str(item.get("source_uptime_percent", "")),
        str(item.get("source_speed", "")),
        iso_value(item.get("source_last_checked")) or "",
        str(item.get("last_error", "") or ""),
        str(item.get("success_count", "")),
        str(item.get("failure_count", "")),
        iso_value(item.get("last_checked")) or "",
        metadata_text,
    ]


PROXY_TABLE_COLUMNS = [
    "id",
    "proxy",
    "protocol",
    "host",
    "port",
    "status",
    "score",
    "latency_ms",
    "country",
    "country_code",
    "city",
    "anonymity",
    "isp",
    "asn",
    "org",
    "ssl",
    "source_latency_ms",
    "source_uptime_percent",
    "source_speed",
    "source_last_checked",
    "last_error",
    "success_count",
    "failure_count",
    "last_checked",
    "metadata",
]
