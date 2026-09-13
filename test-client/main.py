#!/usr/bin/env python3
"""Integration test client for free-proxy-manager."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

DEFAULT_MANAGER_URL = "http://localhost:9321"
DEFAULT_TARGET_URL = "https://www.google.com/"
DEFAULT_TIMEOUT = 20.0
PROXY_CALLS = 10
LIST_PROXY_COUNT = 10

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
        last_checked=_iso(payload.get("last_checked")),
        raw=payload,
    )


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value)


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


def print_pool_diagnostics(diagnostics: PoolDiagnostics) -> None:
    print()
    print("-" * 88)
    print("Pool diagnostics (before tests)")
    print("-" * 88)
    if diagnostics.fetch_error:
        print(f"  warning: {diagnostics.fetch_error}")
    print(f"  /health status: {diagnostics.health_status}")
    print(
        "  pool: "
        f"healthy={diagnostics.pool_healthy} degraded={diagnostics.pool_degraded} "
        f"new={diagnostics.pool_new} checking={diagnostics.pool_checking} "
        f"dead={diagnostics.pool_dead} total={diagnostics.total_proxies}"
    )
    print(
        f"  GET /proxies matching ({diagnostics.list_filter_description}): "
        f"{diagnostics.list_filter_total}"
    )
    print("  note: GET /proxy returns only HEALTHY proxies (outside cooldown)")
    if diagnostics.pool_healthy == 0:
        print(
            "  >> no HEALTHY proxies yet — wait for the checker to finish "
            "(or use --wait-seconds)"
        )
    print("-" * 88)


async def wait_for_healthy_pool(
    client: httpx.AsyncClient,
    manager_url: str,
    *,
    wait_seconds: float,
    poll_seconds: float,
    min_healthy: int,
) -> PoolDiagnostics:
    deadline = time.monotonic() + wait_seconds
    started = time.monotonic()
    last = PoolDiagnostics()
    while time.monotonic() < deadline:
        last = await fetch_pool_diagnostics(
            client,
            manager_url,
            list_protocol="https",
            list_status="HEALTHY",
            list_anonymous=True,
        )
        if last.pool_healthy >= min_healthy:
            waited = time.monotonic() - started
            print(f"Pool ready: {last.pool_healthy} HEALTHY (waited {waited:.0f}s)")
            return last
        remaining = deadline - time.monotonic()
        print(
            f"Waiting for HEALTHY proxies... "
            f"healthy={last.pool_healthy} checking={last.pool_checking} "
            f"new={last.pool_new} ({remaining:.0f}s left)"
        )
        await asyncio.sleep(poll_seconds)
    print("Timed out waiting for HEALTHY proxies.")
    return last


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
        return [], 0, str(exc)

    total = int(payload.get("total") or 0)
    items = payload.get("items", [])
    ranked = sorted(
        items,
        key=lambda item: (-anonymity_rank(item.get("anonymity")), -(item.get("score") or 0)),
    )
    selected = [snapshot_from_api(item) for item in ranked[:pick_count]]
    return selected, total, None


async def test_proxy_against_target(
    proxy: ProxySnapshot,
    target_url: str,
    timeout: float,
) -> tuple[bool, str | None, int | None, float]:
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


async def run_batch(
    manager_url: str,
    target_url: str,
    timeout: float,
    *,
    proxy_calls: int,
    list_count: int,
    list_fetch_limit: int,
    list_protocol: str,
    list_status: str,
    list_anonymous: bool,
    min_score: float | None,
    concurrency: int,
    wait_seconds: float,
    wait_poll_seconds: float,
) -> tuple[list[TestResult], PoolDiagnostics]:
    index = 0

    async with httpx.AsyncClient(timeout=timeout) as manager_client:
        if wait_seconds > 0:
            diagnostics = await wait_for_healthy_pool(
                manager_client,
                manager_url,
                wait_seconds=wait_seconds,
                poll_seconds=wait_poll_seconds,
                min_healthy=1,
            )
        else:
            diagnostics = await fetch_pool_diagnostics(
                manager_client,
                manager_url,
                list_protocol=list_protocol,
                list_status=list_status,
                list_anonymous=list_anonymous,
            )

        print_pool_diagnostics(diagnostics)

        proxy_snapshots: list[tuple[str, int, ProxySnapshot | None, str | None, bool]] = []

        for call in range(1, proxy_calls + 1):
            snapshot, error = await fetch_proxy_from_endpoint(
                manager_client,
                manager_url,
                min_score=min_score,
            )
            proxy_snapshots.append(("GET /proxy", call, snapshot, error, False))

        list_snapshots, list_total, list_error = await fetch_list_proxies(
            manager_client,
            manager_url,
            pick_count=list_count,
            list_limit=list_fetch_limit,
            list_protocol=list_protocol,
            list_status=list_status,
            list_anonymous=list_anonymous,
        )
        if list_error:
            proxy_snapshots.append(("GET /proxies", 0, None, list_error, True))
        elif not list_snapshots:
            proxy_snapshots.append(
                (
                    "GET /proxies",
                    0,
                    None,
                    (
                        f"no proxies match filters ({diagnostics.list_filter_description}); "
                        f"total={list_total}"
                    ),
                    True,
                )
            )
        else:
            for call, snapshot in enumerate(list_snapshots, start=1):
                proxy_snapshots.append(("GET /proxies", call, snapshot, None, False))
            if len(list_snapshots) < list_count:
                proxy_snapshots.append(
                    (
                        "GET /proxies",
                        0,
                        None,
                        (
                            f"only {len(list_snapshots)}/{list_count} proxies matched filters "
                            f"(total={list_total})"
                        ),
                        True,
                    )
                )

    semaphore = asyncio.Semaphore(concurrency)

    async def run_one(
        source: str,
        source_call: int,
        snapshot: ProxySnapshot | None,
        fetch_error: str | None,
        skipped: bool,
    ) -> TestResult:
        nonlocal index
        index += 1
        current_index = index
        tested_at = datetime.now(UTC).isoformat()

        if skipped:
            return TestResult(
                index=current_index,
                source=source,
                source_call=source_call,
                proxy=None,
                fetch_ok=False,
                fetch_error=fetch_error,
                test_ok=False,
                test_error=fetch_error or "skipped",
                http_status=None,
                response_time_ms=None,
                tested_at=tested_at,
                skipped=True,
            )

        if snapshot is None:
            return TestResult(
                index=current_index,
                source=source,
                source_call=source_call,
                proxy=None,
                fetch_ok=False,
                fetch_error=fetch_error,
                test_ok=False,
                test_error=fetch_error or "proxy not fetched",
                http_status=None,
                response_time_ms=None,
                tested_at=tested_at,
            )

        async with semaphore:
            ok, error, status, elapsed = await test_proxy_against_target(
                snapshot,
                target_url,
                timeout,
            )

        return TestResult(
            index=current_index,
            source=source,
            source_call=source_call,
            proxy=snapshot,
            fetch_ok=True,
            fetch_error=None,
            test_ok=ok,
            test_error=error,
            http_status=status,
            response_time_ms=elapsed,
            tested_at=tested_at,
        )

    tasks = [
        run_one(source, source_call, snapshot, fetch_error, skipped)
        for source, source_call, snapshot, fetch_error, skipped in proxy_snapshots
    ]
    results = list(await asyncio.gather(*tasks))
    return results, diagnostics


def print_report(
    results: list[TestResult],
    target_url: str,
    manager_url: str,
    diagnostics: PoolDiagnostics,
) -> None:
    executed = [item for item in results if not item.skipped]
    ok_count = sum(1 for item in executed if item.test_ok)
    fail_count = len(executed) - ok_count
    skipped = [item for item in results if item.skipped]

    print()
    print("=" * 88)
    print("free-proxy-manager test-client report")
    print("=" * 88)
    print(f"Manager: {manager_url}")
    print(f"Target:  {target_url}")
    print(
        f"Tests:   {len(executed)} executed, {len(skipped)} skipped | "
        f"OK: {ok_count} | FAIL: {fail_count}"
    )
    print("=" * 88)

    for item in results:
        if item.skipped:
            print()
            print(f"[--] SKIP | {item.source} | {item.fetch_error}")
            continue

        status_label = "OK" if item.test_ok else "FAIL"
        proxy_label = item.proxy.proxy_url if item.proxy else "(none)"
        print()
        print(f"[{item.index:02d}] {status_label} | {item.source} #{item.source_call}")
        print(f"     proxy: {proxy_label}")
        if item.proxy:
            print(
                "     meta: "
                f"status={item.proxy.status} score={item.proxy.score} "
                f"anonymity={item.proxy.anonymity} country={item.proxy.country_code} "
                f"manager_latency_ms={item.proxy.latency_ms}"
            )
        if not item.fetch_ok:
            print(f"     fetch_error: {item.fetch_error}")
        print(
            f"     test: http={item.http_status} "
            f"response_time_ms={item.response_time_ms} error={item.test_error}"
        )

    print()
    print("-" * 88)
    print("Summary by source")
    for source in ("GET /proxy", "GET /proxies"):
        subset = [item for item in executed if item.source == source]
        subset_ok = sum(1 for item in subset if item.test_ok)
        print(f"  {source}: {subset_ok}/{len(subset)} OK")
    if diagnostics.pool_healthy == 0:
        print()
        print("Hint: pool has no HEALTHY proxies. The checker may still be warming up.")
        print("  - watch logs for 'check succeeded' and 'Checker queue refilled'")
        print("  - retry with: python main.py --wait-seconds 300")
    print("=" * 88)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Test free-proxy-manager proxies against Google.")
    parser.add_argument(
        "--manager-url",
        default=os.getenv("PROXY_MANAGER_URL", DEFAULT_MANAGER_URL),
        help=f"Base URL of free-proxy-manager (default: {DEFAULT_MANAGER_URL})",
    )
    parser.add_argument(
        "--target-url",
        default=os.getenv("TEST_TARGET_URL", DEFAULT_TARGET_URL),
        help=f"URL accessed through each proxy (default: {DEFAULT_TARGET_URL})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("TEST_TIMEOUT", DEFAULT_TIMEOUT)),
        help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--proxy-calls",
        type=int,
        default=PROXY_CALLS,
        help=f"Number of GET /proxy calls (default: {PROXY_CALLS})",
    )
    parser.add_argument(
        "--list-count",
        type=int,
        default=LIST_PROXY_COUNT,
        help="Proxies to pick from one GET /proxies (default: 10)",
    )
    parser.add_argument(
        "--list-protocol",
        default="https",
        help="Protocol filter for GET /proxies batch (default: https)",
    )
    parser.add_argument(
        "--list-fetch-limit",
        type=int,
        default=100,
        help="How many proxies to request from /proxies before ranking by anonymity",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=None,
        help="Optional min_score passed to GET /proxy",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Max concurrent proxy probes",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=0,
        help="Wait up to N seconds for at least one HEALTHY proxy before testing",
    )
    parser.add_argument(
        "--wait-poll-seconds",
        type=float,
        default=5,
        help="Poll interval when using --wait-seconds (default: 5)",
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        metavar="PATH",
        help="Optional path to save full report as JSON",
    )
    return parser


def serialize_results(results: list[TestResult]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for item in results:
        row = asdict(item)
        if item.proxy is not None:
            row["proxy"] = asdict(item.proxy)
        payload.append(row)
    return payload


async def async_main(args: argparse.Namespace) -> int:
    print(f"Manager: {args.manager_url}")
    print(f"Target:  {args.target_url}")
    print(
        f"Plan: {args.proxy_calls}x GET /proxy + "
        f"1x GET /proxies -> {args.list_count} "
        f"{args.list_protocol.upper()} HEALTHY anonymous proxies"
    )

    results, diagnostics = await run_batch(
        args.manager_url,
        args.target_url,
        args.timeout,
        proxy_calls=args.proxy_calls,
        list_count=args.list_count,
        list_fetch_limit=args.list_fetch_limit,
        list_protocol=args.list_protocol,
        list_status="HEALTHY",
        list_anonymous=True,
        min_score=args.min_score,
        concurrency=args.concurrency,
        wait_seconds=args.wait_seconds,
        wait_poll_seconds=args.wait_poll_seconds,
    )

    print_report(results, args.target_url, args.manager_url, diagnostics)

    if args.json_path:
        report = {
            "manager_url": args.manager_url,
            "target_url": args.target_url,
            "generated_at": datetime.now(UTC).isoformat(),
            "diagnostics": asdict(diagnostics),
            "results": serialize_results(results),
        }
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, ensure_ascii=False)
        print(f"JSON report saved to {args.json_path}")

    executed = [item for item in results if not item.skipped]
    if not executed:
        return 2
    return 0 if all(item.test_ok for item in executed if item.fetch_ok) else 1


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(async_main(args)))
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
