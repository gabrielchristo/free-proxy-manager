from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import httpx

from client_lib.api import (
    fetch_list_proxies,
    fetch_pool_diagnostics,
    fetch_proxy_from_endpoint,
    test_proxy_against_target,
)
from client_lib.models import PoolDiagnostics, ProxySnapshot, TestResult


def format_pool_diagnostics(diagnostics: PoolDiagnostics) -> str:
    lines = [
        "",
        "-" * 88,
        "Pool diagnostics (before tests)",
        "-" * 88,
    ]
    if diagnostics.fetch_error:
        lines.append(f"  warning: {diagnostics.fetch_error}")
    lines.append(f"  /health status: {diagnostics.health_status}")
    lines.append(
        "  pool: "
        f"healthy={diagnostics.pool_healthy} degraded={diagnostics.pool_degraded} "
        f"new={diagnostics.pool_new} checking={diagnostics.pool_checking} "
        f"dead={diagnostics.pool_dead} total={diagnostics.total_proxies}"
    )
    lines.append(
        f"  GET /proxies matching ({diagnostics.list_filter_description}): "
        f"{diagnostics.list_filter_total}"
    )
    lines.append("  note: GET /proxy returns only HEALTHY proxies (outside cooldown)")
    if diagnostics.pool_healthy == 0:
        lines.append(
            "  >> no HEALTHY proxies yet — wait for the checker to finish "
            "(or increase wait seconds)"
        )
    lines.append("-" * 88)
    return "\n".join(lines)


async def wait_for_healthy_pool(
    client: httpx.AsyncClient,
    manager_url: str,
    *,
    wait_seconds: float,
    poll_seconds: float,
    min_healthy: int,
    on_progress: Callable[[str], None] | None = None,
) -> PoolDiagnostics:
    deadline = time.monotonic() + wait_seconds
    started = time.monotonic()
    last = PoolDiagnostics()
    while time.monotonic() < deadline:
        last = await fetch_pool_diagnostics(
            client,
            manager_url,
            list_protocol="http",
            list_status="HEALTHY",
            list_anonymous=True,
        )
        if last.pool_healthy >= min_healthy:
            waited = time.monotonic() - started
            message = f"Pool ready: {last.pool_healthy} HEALTHY (waited {waited:.0f}s)"
            if on_progress:
                on_progress(message)
            return last
        remaining = deadline - time.monotonic()
        message = (
            f"Waiting for HEALTHY proxies... "
            f"healthy={last.pool_healthy} checking={last.pool_checking} "
            f"new={last.pool_new} ({remaining:.0f}s left)"
        )
        if on_progress:
            on_progress(message)
        await asyncio.sleep(poll_seconds)
    if on_progress:
        on_progress("Timed out waiting for HEALTHY proxies.")
    return last


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
    on_progress: Callable[[str], None] | None = None,
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
                on_progress=on_progress,
            )
        else:
            diagnostics = await fetch_pool_diagnostics(
                manager_client,
                manager_url,
                list_protocol=list_protocol,
                list_status=list_status,
                list_anonymous=list_anonymous,
            )

        if on_progress:
            on_progress(format_pool_diagnostics(diagnostics))

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


def format_report(
    results: list[TestResult],
    target_url: str,
    manager_url: str,
    diagnostics: PoolDiagnostics,
) -> str:
    executed = [item for item in results if not item.skipped]
    ok_count = sum(1 for item in executed if item.test_ok)
    fail_count = len(executed) - ok_count
    skipped = [item for item in results if item.skipped]

    lines = [
        "",
        "=" * 88,
        "free-proxy-manager test-client report",
        "=" * 88,
        f"Manager: {manager_url}",
        f"Target:  {target_url}",
        f"Tests:   {len(executed)} executed, {len(skipped)} skipped | "
        f"OK: {ok_count} | FAIL: {fail_count}",
        "=" * 88,
    ]

    for item in results:
        if item.skipped:
            lines.extend(["", f"[--] SKIP | {item.source} | {item.fetch_error}"])
            continue

        status_label = "OK" if item.test_ok else "FAIL"
        proxy_label = item.proxy.proxy_url if item.proxy else "(none)"
        lines.extend(["", f"[{item.index:02d}] {status_label} | {item.source} #{item.source_call}"])
        lines.append(f"     proxy: {proxy_label}")
        if item.proxy:
            lines.append(
                "     meta: "
                f"status={item.proxy.status} score={item.proxy.score} "
                f"anonymity={item.proxy.anonymity} country={item.proxy.country_code} "
                f"manager_latency_ms={item.proxy.latency_ms}"
            )
        if not item.fetch_ok:
            lines.append(f"     fetch_error: {item.fetch_error}")
        lines.append(
            f"     test: http={item.http_status} "
            f"response_time_ms={item.response_time_ms} error={item.test_error}"
        )

    lines.extend(["", "-" * 88, "Summary by source"])
    for source in ("GET /proxy", "GET /proxies"):
        subset = [item for item in executed if item.source == source]
        subset_ok = sum(1 for item in subset if item.test_ok)
        lines.append(f"  {source}: {subset_ok}/{len(subset)} OK")
    if diagnostics.pool_healthy == 0:
        lines.extend(
            [
                "",
                "Hint: pool has no HEALTHY proxies. The checker may still be warming up.",
                "  - watch logs for 'check succeeded' and 'Checker queue refilled'",
                "  - retry with a longer wait",
            ]
        )
    lines.append("=" * 88)
    return "\n".join(lines)


def serialize_results(results: list[TestResult]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for item in results:
        row = asdict(item)
        if item.proxy is not None:
            row["proxy"] = asdict(item.proxy)
        payload.append(row)
    return payload
