import pytest

from app.config import get_settings
from app.models import Proxy, ProxySource, ProxyStatus
from app.services.collector import CollectorService
from app.services.proxy_identity import normalize_host, prefer_protocol, proxy_identity
from app.sources.base import CollectedProxy


def test_normalize_host_canonicalizes_ipv4():
    assert normalize_host("010.000.000.001") == "10.0.0.1"
    assert normalize_host(" 10.0.0.1 ") == "10.0.0.1"


def test_normalize_host_lowercases_hostnames():
    assert normalize_host("Proxy.Example.COM.") == "proxy.example.com"


def test_prefer_protocol_chooses_https():
    assert prefer_protocol("http", "https") == "https"
    assert prefer_protocol("https", "http") == "https"


def test_persist_collected_merges_http_and_https(db_session):
    source = ProxySource(
        name="dedup-test",
        url="https://example.com/list",
        enabled=True,
        priority=50,
    )
    db_session.add(source)
    db_session.commit()
    source_id = source.id

    service = CollectorService(settings=get_settings())
    http_item = CollectedProxy(host="10.0.0.1", port=8080, protocol="http")
    https_item = CollectedProxy(host="10.0.0.1", port=8080, protocol="https")

    service._persist_collected(db_session, source_id, "dedup-test", [http_item])
    service._persist_collected(db_session, source_id, "dedup-test", [https_item])

    rows = db_session.query(Proxy).all()
    assert len(rows) == 1
    assert rows[0].host == "10.0.0.1"
    assert rows[0].port == 8080
    assert rows[0].protocol == "https"


def test_total_proxies_found_counts_unique_source_links(db_session):
    source = ProxySource(
        name="total-found",
        url="https://example.com/list",
        enabled=True,
        priority=50,
    )
    db_session.add(source)
    db_session.commit()
    source_id = source.id

    service = CollectorService(settings=get_settings())
    batch_one = [
        CollectedProxy(host="10.0.0.1", port=8080, protocol="http"),
        CollectedProxy(host="10.0.0.2", port=8080, protocol="http"),
    ]
    batch_two = [
        CollectedProxy(host="10.0.0.1", port=8080, protocol="http"),
        CollectedProxy(host="10.0.0.3", port=8080, protocol="http"),
    ]

    service._persist_collected(db_session, source_id, "total-found", batch_one)
    db_session.query(ProxySource).filter(ProxySource.id == source_id).update(
        {
            ProxySource.proxies_found: len(batch_one),
            ProxySource.total_proxies_found: service._count_source_links(
                db_session, source_id
            ),
        }
    )
    db_session.commit()

    service._persist_collected(db_session, source_id, "total-found", batch_two)
    db_session.query(ProxySource).filter(ProxySource.id == source_id).update(
        {
            ProxySource.proxies_found: len(batch_two),
            ProxySource.total_proxies_found: service._count_source_links(
                db_session, source_id
            ),
        }
    )
    db_session.commit()

    db_session.expire_all()
    updated = db_session.query(ProxySource).filter(ProxySource.id == source_id).one()
    assert updated.proxies_found == 2
    assert updated.total_proxies_found == 3


def test_persist_collected_deduplicates_normalized_hosts(db_session):
    source = ProxySource(
        name="dedup-normalize",
        url="https://example.com/list",
        enabled=True,
        priority=50,
    )
    db_session.add(source)
    db_session.commit()
    source_id = source.id

    service = CollectorService(settings=get_settings())
    items = [
        CollectedProxy(host="010.000.000.001", port=8080, protocol="http"),
        CollectedProxy(host="10.0.0.1", port=8080, protocol="http"),
    ]

    service._persist_collected(db_session, source_id, "dedup-normalize", items)

    rows = db_session.query(Proxy).all()
    assert len(rows) == 1
    assert rows[0].host == "10.0.0.1"


def test_persist_collected_keeps_socks_separate_from_http(db_session):
    source = ProxySource(
        name="socks-dedup",
        url="https://example.com/list",
        enabled=True,
        priority=50,
    )
    db_session.add(source)
    db_session.commit()
    source_id = source.id

    service = CollectorService(settings=get_settings())
    items = [
        CollectedProxy(host="10.0.0.1", port=1080, protocol="http"),
        CollectedProxy(host="10.0.0.1", port=1080, protocol="socks5"),
        CollectedProxy(host="10.0.0.1", port=1080, protocol="socks4"),
    ]

    service._persist_collected(db_session, source_id, "socks-dedup", items)

    rows = db_session.query(Proxy).order_by(Proxy.protocol).all()
    assert len(rows) == 3
    assert [row.protocol for row in rows] == ["http", "socks4", "socks5"]


def test_proxy_identity_returns_normalized_pair():
    assert proxy_identity("010.000.000.001", 8080) == ("10.0.0.1", 8080)
