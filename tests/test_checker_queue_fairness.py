from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.jobs.checker_job import QUEUE_STATE_ORDER, CheckerJob
from app.models import Proxy, ProxyStatus


def test_allocate_state_slots_splits_evenly():
    assert CheckerJob._allocate_state_slots(40, 4) == [10, 10, 10, 10]
    assert CheckerJob._allocate_state_slots(41, 4) == [11, 10, 10, 10]
    assert CheckerJob._allocate_state_slots(0, 4) == []


def test_round_robin_state_pools_interleaves_status_tiers():
    pools = {
        "healthy": [1, 2],
        "new": [11, 12],
        "degraded": [21],
        "dead": [31, 32, 33],
    }

    collected = CheckerJob._round_robin_state_pools(pools, limit=6)

    assert collected == [1, 11, 21, 31, 2, 12]


def test_fetch_queue_batch_balances_status_tiers(db_session):
    now = datetime.now(UTC)
    recheck_cutoff = now - timedelta(seconds=get_settings().recheck_interval + 60)

    for index in range(8):
        db_session.add(
            Proxy(
                host=f"10.0.1.{index}",
                port=8000 + index,
                protocol="http",
                status=ProxyStatus.HEALTHY,
                last_checked=recheck_cutoff,
            )
        )
        db_session.add(
            Proxy(
                host=f"10.0.2.{index}",
                port=8000 + index,
                protocol="http",
                status=ProxyStatus.NEW,
            )
        )
        db_session.add(
            Proxy(
                host=f"10.0.3.{index}",
                port=8000 + index,
                protocol="http",
                status=ProxyStatus.DEGRADED,
            )
        )
        db_session.add(
            Proxy(
                host=f"10.0.4.{index}",
                port=8000 + index,
                protocol="http",
                status=ProxyStatus.DEAD,
                cooldown_until=now - timedelta(minutes=1),
            )
        )
    db_session.commit()

    job = CheckerJob(queue=None, settings=get_settings())  # type: ignore[arg-type]
    proxy_ids, _ = job._fetch_queue_batch_ids(db_session, limit=40, exclude_ids=frozenset())

    assert len(proxy_ids) == 32
    rows = db_session.query(Proxy.id, Proxy.status).filter(Proxy.id.in_(proxy_ids)).all()
    status_map = {
        ProxyStatus.HEALTHY: "healthy",
        ProxyStatus.NEW: "new",
        ProxyStatus.DEGRADED: "degraded",
        ProxyStatus.DEAD: "dead",
    }
    tier_counts = {key: 0 for key in QUEUE_STATE_ORDER}
    for _, status in rows:
        tier_counts[status_map[status]] += 1

    assert tier_counts == {"healthy": 8, "new": 8, "degraded": 8, "dead": 8}


def test_fetch_queue_batch_redistributes_unused_slots(db_session):
    now = datetime.now(UTC)
    recheck_cutoff = now - timedelta(seconds=get_settings().recheck_interval + 60)

    db_session.add(
        Proxy(
            host="10.0.0.1",
            port=8080,
            protocol="http",
            status=ProxyStatus.HEALTHY,
            last_checked=recheck_cutoff,
        )
    )
    for index in range(6):
        db_session.add(
            Proxy(
                host=f"10.0.2.{index}",
                port=8100 + index,
                protocol="http",
                status=ProxyStatus.NEW,
            )
        )
    db_session.commit()

    job = CheckerJob(queue=None, settings=get_settings())  # type: ignore[arg-type]
    proxy_ids, _ = job._fetch_queue_batch_ids(db_session, limit=8, exclude_ids=frozenset())

    assert len(proxy_ids) == 7
    statuses = {
        status
        for status, in db_session.query(Proxy.status)
        .filter(Proxy.id.in_(proxy_ids))
        .all()
    }
    assert ProxyStatus.HEALTHY in statuses
    assert ProxyStatus.NEW in statuses
