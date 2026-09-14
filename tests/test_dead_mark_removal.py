from app.config import get_settings
from app.jobs.checker_job import CheckerJob
from app.models import Proxy, ProxySource, ProxySourceLink, ProxyStatus
from app.services.checker import CheckResult


def test_success_resets_consecutive_dead_marks(db_session):
    proxy = Proxy(
        host="10.0.0.1",
        port=8080,
        protocol="http",
        status=ProxyStatus.DEGRADED,
        consecutive_failures=1,
        consecutive_dead_marks=3,
    )
    db_session.add(proxy)
    db_session.commit()

    job = CheckerJob(queue=None, settings=get_settings())  # type: ignore[arg-type]
    removed = job._apply_result(db_session, proxy, CheckResult(success=True, latency_ms=100.0))

    assert removed is False
    assert proxy.status == ProxyStatus.HEALTHY
    assert proxy.consecutive_dead_marks == 0


def test_dead_mark_increments_on_dead_transition(db_session):
    proxy = Proxy(
        host="10.0.0.2",
        port=8080,
        protocol="http",
        status=ProxyStatus.DEGRADED,
        consecutive_failures=2,
        consecutive_dead_marks=2,
    )
    db_session.add(proxy)
    db_session.commit()
    proxy_id = proxy.id

    job = CheckerJob(queue=None, settings=get_settings())  # type: ignore[arg-type]
    removed = job._apply_result(db_session, proxy, CheckResult(success=False, error="timeout"))

    assert removed is False
    assert proxy.status == ProxyStatus.DEAD
    assert proxy.consecutive_dead_marks == 3
    assert db_session.query(Proxy).filter(Proxy.id == proxy_id).one_or_none() is not None


def test_seventh_consecutive_dead_mark_removes_proxy(db_session):
    source = ProxySource(
        name="dead-mark-test",
        url="https://example.com/list",
        enabled=True,
        priority=50,
    )
    proxy = Proxy(
        host="10.0.0.3",
        port=8080,
        protocol="http",
        status=ProxyStatus.DEGRADED,
        consecutive_failures=2,
        consecutive_dead_marks=6,
        success_count=10,
        last_success=None,
    )
    db_session.add(source)
    db_session.add(proxy)
    db_session.flush()
    db_session.add(ProxySourceLink(proxy_id=proxy.id, source_id=source.id))
    db_session.commit()
    proxy_id = proxy.id

    job = CheckerJob(queue=None, settings=get_settings())  # type: ignore[arg-type]
    removed = job._apply_result(db_session, proxy, CheckResult(success=False, error="timeout"))
    db_session.commit()

    assert removed is True
    assert db_session.query(Proxy).filter(Proxy.id == proxy_id).one_or_none() is None
    assert (
        db_session.query(ProxySourceLink)
        .filter(ProxySourceLink.proxy_id == proxy_id)
        .count()
        == 0
    )
