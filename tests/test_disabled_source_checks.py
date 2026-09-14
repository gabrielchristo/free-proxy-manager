from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.jobs.checker_job import CheckerJob
from app.models import Proxy, ProxySource, ProxySourceLink, ProxyStatus
from app.services.collector import CollectorService
from app.sources.config import SourcesConfig


def test_sync_sources_from_config_updates_disabled_flag(db_session, monkeypatch, tmp_path):
    config_path = tmp_path / "sources.json"
    config_path.write_text(
        SourcesConfig.model_validate(
            {
                "fetch_timeout": 30,
                "sources": [
                    {
                        "name": "nodemaven",
                        "type": "nodemaven",
                        "enabled": False,
                        "url": "https://freeproxies.nodemaven.com/proxies",
                        "priority": 65,
                        "protocols": ["http", "https"],
                    }
                ],
            }
        ).model_dump_json(),
        encoding="utf-8",
    )

    db_session.add(
        ProxySource(
            name="nodemaven",
            url="https://old.example/proxies",
            enabled=True,
            priority=65,
        )
    )
    db_session.commit()

    settings = get_settings().model_copy(update={"sources_config_path": str(config_path)})
    monkeypatch.setattr("app.services.collector.SessionLocal", lambda: db_session)

    CollectorService(settings=settings).sync_sources_from_config()

    source = db_session.query(ProxySource).filter(ProxySource.name == "nodemaven").one()
    assert source.enabled is False
    assert source.url == "https://freeproxies.nodemaven.com/proxies"


def test_fetch_queue_batch_skips_proxies_from_disabled_sources_only(db_session):
    enabled_source = ProxySource(
        name="enabled-source",
        url="https://example.com/enabled",
        enabled=True,
        priority=100,
    )
    disabled_source = ProxySource(
        name="disabled-source",
        url="https://example.com/disabled",
        enabled=False,
        priority=50,
    )
    db_session.add_all([enabled_source, disabled_source])
    db_session.flush()

    enabled_proxy = Proxy(host="10.0.0.1", port=8080, protocol="http", status=ProxyStatus.NEW)
    disabled_only_proxy = Proxy(
        host="10.0.0.2",
        port=8080,
        protocol="http",
        status=ProxyStatus.NEW,
    )
    db_session.add_all([enabled_proxy, disabled_only_proxy])
    db_session.flush()

    db_session.add(ProxySourceLink(proxy_id=enabled_proxy.id, source_id=enabled_source.id))
    db_session.add(
        ProxySourceLink(proxy_id=disabled_only_proxy.id, source_id=disabled_source.id)
    )
    db_session.commit()

    job = CheckerJob(queue=None, settings=get_settings())  # type: ignore[arg-type]
    proxy_ids, _ = job._fetch_queue_batch_ids(db_session, limit=10, exclude_ids=frozenset())

    assert enabled_proxy.id in proxy_ids
    assert disabled_only_proxy.id not in proxy_ids


def test_fetch_queue_batch_keeps_proxy_linked_to_enabled_and_disabled(db_session):
    enabled_source = ProxySource(
        name="enabled-source",
        url="https://example.com/enabled",
        enabled=True,
        priority=100,
    )
    disabled_source = ProxySource(
        name="disabled-source",
        url="https://example.com/disabled",
        enabled=False,
        priority=50,
    )
    db_session.add_all([enabled_source, disabled_source])
    db_session.flush()

    shared_proxy = Proxy(host="10.0.0.3", port=8080, protocol="http", status=ProxyStatus.NEW)
    db_session.add(shared_proxy)
    db_session.flush()
    db_session.add(ProxySourceLink(proxy_id=shared_proxy.id, source_id=enabled_source.id))
    db_session.add(ProxySourceLink(proxy_id=shared_proxy.id, source_id=disabled_source.id))
    db_session.commit()

    job = CheckerJob(queue=None, settings=get_settings())  # type: ignore[arg-type]
    proxy_ids, _ = job._fetch_queue_batch_ids(db_session, limit=10, exclude_ids=frozenset())

    assert shared_proxy.id in proxy_ids


def test_mark_checking_skips_proxy_without_enabled_source(db_session, monkeypatch):
    monkeypatch.setattr("app.jobs.checker_job.SessionLocal", lambda: db_session)

    disabled_source = ProxySource(
        name="disabled-source",
        url="https://example.com/disabled",
        enabled=False,
        priority=50,
    )
    proxy = Proxy(host="10.0.0.4", port=8080, protocol="http", status=ProxyStatus.NEW)
    db_session.add_all([disabled_source, proxy])
    db_session.flush()
    db_session.add(ProxySourceLink(proxy_id=proxy.id, source_id=disabled_source.id))
    db_session.commit()

    job = CheckerJob(queue=None, settings=get_settings())  # type: ignore[arg-type]
    target = job._mark_checking(proxy.id)

    assert target is None
    assert (
        db_session.query(Proxy).filter(Proxy.id == proxy.id).one().status == ProxyStatus.NEW
    )


def test_fetch_queue_batch_skips_healthy_from_disabled_source(db_session):
    now = datetime.now(UTC)
    recheck_cutoff = now - timedelta(seconds=get_settings().recheck_interval + 60)

    disabled_source = ProxySource(
        name="disabled-source",
        url="https://example.com/disabled",
        enabled=False,
        priority=50,
    )
    proxy = Proxy(
        host="10.0.0.5",
        port=8080,
        protocol="http",
        status=ProxyStatus.HEALTHY,
        last_checked=recheck_cutoff,
    )
    db_session.add_all([disabled_source, proxy])
    db_session.flush()
    db_session.add(ProxySourceLink(proxy_id=proxy.id, source_id=disabled_source.id))
    db_session.commit()

    job = CheckerJob(queue=None, settings=get_settings())  # type: ignore[arg-type]
    proxy_ids, _ = job._fetch_queue_batch_ids(db_session, limit=10, exclude_ids=frozenset())

    assert proxy.id not in proxy_ids
