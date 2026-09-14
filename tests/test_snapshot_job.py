from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.jobs.snapshot_job import SnapshotJob
from app.models import PoolSnapshot, Proxy, ProxyStatus


def test_snapshot_job_records_pool_counts(db_session):
    db_session.add_all(
        [
            Proxy(
                host="1.1.1.1",
                port=8080,
                protocol="http",
                status=ProxyStatus.HEALTHY,
            ),
            Proxy(
                host="2.2.2.2",
                port=8080,
                protocol="http",
                status=ProxyStatus.DEAD,
            ),
        ]
    )
    db_session.commit()

    SnapshotJob(get_settings()).run(db_session)

    snapshot = db_session.query(PoolSnapshot).one()
    assert snapshot.total_proxies == 2
    assert snapshot.healthy == 1
    assert snapshot.dead == 1


def test_snapshot_job_prunes_old_rows(db_session):
    settings = get_settings().model_copy(update={"stats_snapshot_retention_days": 7})
    old = PoolSnapshot(
        recorded_at=datetime.now(UTC) - timedelta(days=10),
        total_proxies=1,
        healthy=0,
        degraded=0,
        dead=1,
        new=0,
        checking=0,
        disabled=0,
        in_cooldown=0,
    )
    db_session.add(old)
    db_session.commit()
    old_id = old.id

    SnapshotJob(settings).run(db_session)

    rows = db_session.query(PoolSnapshot).order_by(PoolSnapshot.id).all()
    assert len(rows) == 1
    assert rows[0].id != old_id


def test_get_snapshot_history(db_session):
    db_session.add(
        PoolSnapshot(
            recorded_at=datetime.now(UTC) - timedelta(hours=1),
            total_proxies=100,
            healthy=5,
            degraded=0,
            dead=90,
            new=3,
            checking=1,
            disabled=1,
            in_cooldown=10,
        )
    )
    db_session.commit()

    from app.services.pool import PoolService

    history = PoolService(get_settings()).get_snapshot_history(
        db_session,
        hours=24,
        limit=10,
    )
    assert history.count == 1
    assert history.items[0].pool.healthy == 5
    assert history.items[0].pool.dead == 90


def test_stats_history_accepts_month_window(client):
    response = client.get("/stats/history", params={"hours": 720, "limit": 8640})
    assert response.status_code == 200
    payload = response.json()
    assert payload["hours"] == 720
    assert payload["count"] == 0
