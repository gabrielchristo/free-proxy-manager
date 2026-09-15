from app.config import get_settings
from app.models import Proxy, ProxySource
from app.services.collector import CollectorService
from app.services.checker import CheckerService
from app.sources.base import CollectedProxy


def test_persist_collected_commits_in_batches(db_session):
    source = ProxySource(
        name="batch-test",
        url="https://example.com/list",
        enabled=True,
        priority=50,
    )
    db_session.add(source)
    db_session.commit()

    collected = [
        CollectedProxy(host=f"10.0.0.{index}", port=8000 + index, protocol="http")
        for index in range(5)
    ]

    settings = get_settings().model_copy(update={"collector_persist_batch_size": 2})
    service = CollectorService(settings=settings)

    commit_calls = 0
    expunge_calls = 0
    original_commit = db_session.commit
    original_expunge = db_session.expunge_all

    def counting_commit():
        nonlocal commit_calls
        commit_calls += 1
        original_commit()

    def counting_expunge():
        nonlocal expunge_calls
        expunge_calls += 1
        original_expunge()

    db_session.commit = counting_commit
    db_session.expunge_all = counting_expunge

    queued_ids = service._persist_collected(db_session, source.id, source.name, collected)

    assert len(queued_ids) == 5
    assert commit_calls == 3
    assert expunge_calls == 3

    db_session.expunge_all()
    assert db_session.query(Proxy).count() == 5


def test_persist_collected_for_source_updates_totals_after_batch_expunge(db_session, monkeypatch):
    monkeypatch.setattr("app.services.collector.SessionLocal", lambda: db_session)

    settings = get_settings().model_copy(update={"collector_persist_batch_size": 2})
    service = CollectorService(settings=settings)

    collected = [
        CollectedProxy(host=f"10.0.0.{index}", port=8000 + index, protocol="http")
        for index in range(5)
    ]

    queued_ids = service.persist_collected_for_source(
        "batch-expunge",
        "https://example.com/list",
        50,
        collected,
    )

    source = db_session.query(ProxySource).filter(ProxySource.name == "batch-expunge").one()
    assert len(queued_ids) == 5
    assert source.proxies_found == 5
    assert source.total_proxies_found == 5
    assert source.last_success is not None
    assert source.last_error is None


def test_proxy_connect_url_uses_http_for_https_tagged_proxies():
    settings = get_settings().model_copy(update={"check_https_proxy_as_http": True})
    service = CheckerService(settings)

    assert service.proxy_connect_url("1.2.3.4", 8080, "https") == "http://1.2.3.4:8080"
    assert service.proxy_connect_url("1.2.3.4", 8080, "http") == "http://1.2.3.4:8080"


def test_proxy_connect_url_keeps_socks_scheme():
    settings = get_settings().model_copy(update={"check_https_proxy_as_http": True})
    service = CheckerService(settings)

    assert service.proxy_connect_url("1.2.3.4", 1080, "socks5") == "socks5://1.2.3.4:1080"
    assert service.proxy_connect_url("1.2.3.4", 1080, "socks4") == "socks4://1.2.3.4:1080"


def test_proxy_connect_url_keeps_https_when_disabled():
    settings = get_settings().model_copy(update={"check_https_proxy_as_http": False})
    service = CheckerService(settings)

    assert service.proxy_connect_url("1.2.3.4", 8080, "https") == "https://1.2.3.4:8080"
