import asyncio

import pytest

from app.config import get_settings
from app.jobs.checker_job import CheckerJob, ProxyCheckTarget
from app.models import Proxy, ProxyStatus
from app.services.connectivity import ConnectivityGuard


@pytest.mark.asyncio
async def test_connectivity_guard_disabled_always_available():
    settings = get_settings().model_copy(update={"connectivity_check_enabled": False})
    guard = ConnectivityGuard(settings)
    assert await guard.is_available() is True


@pytest.mark.asyncio
async def test_is_available_reads_cached_state_without_probe(monkeypatch):
    guard = ConnectivityGuard(get_settings())
    guard._available = False
    guard._checked_at = 0.0

    async def fail_if_called() -> bool:
        raise AssertionError("probe should not run from is_available()")

    monkeypatch.setattr(guard, "_probe", fail_if_called)
    assert await guard.is_available() is False


@pytest.mark.asyncio
async def test_probe_loop_refreshes_on_interval(monkeypatch):
    settings = get_settings().model_copy(update={"connectivity_check_interval": 1})
    guard = ConnectivityGuard(settings)
    calls = {"count": 0}

    async def fake_probe() -> bool:
        calls["count"] += 1
        return calls["count"] % 2 == 1

    monkeypatch.setattr(guard, "_probe", fake_probe)

    await guard.start()
    assert calls["count"] == 1
    assert await guard.is_available() is True

    await asyncio.sleep(1.1)
    assert calls["count"] >= 2
    assert await guard.is_available() is False

    await guard.close()


def test_revert_check_restores_previous_status(db_session, monkeypatch):
    monkeypatch.setattr("app.jobs.checker_job.SessionLocal", lambda: db_session)

    proxy = Proxy(
        host="10.0.0.1",
        port=8080,
        protocol="http",
        status=ProxyStatus.CHECKING,
        success_count=5,
        consecutive_failures=0,
    )
    db_session.add(proxy)
    db_session.commit()
    proxy_id = proxy.id

    job = CheckerJob(asyncio.Queue(), get_settings())
    target = ProxyCheckTarget(
        proxy_id=proxy_id,
        host=proxy.host,
        port=proxy.port,
        protocol=proxy.protocol,
        url=proxy.url,
        source_label="test",
        previous_status=ProxyStatus.HEALTHY.value,
    )

    job._revert_check(target)
    updated = db_session.query(Proxy).filter(Proxy.id == proxy_id).one()

    assert updated.status == ProxyStatus.HEALTHY
    assert updated.consecutive_failures == 0
    assert updated.success_count == 5
