from datetime import UTC, datetime

from app.models import Proxy
from app.services.collector_helpers import apply_collected_fields, build_source_metadata
from app.sources.base import CollectedProxy


def test_apply_collected_fields_persists_structured_and_metadata_values():
    proxy = Proxy(host="1.2.3.4", port=8080, protocol="http")
    item = CollectedProxy(
        host="1.2.3.4",
        port=8080,
        protocol="http",
        country="Brazil",
        country_code="BR",
        city="Sao Paulo",
        isp="Example ISP",
        asn="AS12345",
        source_latency_ms=120.5,
        source_uptime_percent=98.2,
        metadata={"google": True, "responseTime": 2500},
    )

    apply_collected_fields(proxy, item)

    assert proxy.country == "Brazil"
    assert proxy.country_code == "BR"
    assert proxy.city == "Sao Paulo"
    assert proxy.isp == "Example ISP"
    assert proxy.asn == "AS12345"
    assert proxy.source_latency_ms == 120.5
    assert proxy.source_uptime_percent == 98.2
    assert proxy.metadata_json == {"google": True, "responseTime": 2500}


def test_build_source_metadata_includes_source_snapshot():
    checked_at = datetime(2026, 3, 22, 12, 0, tzinfo=UTC)
    item = CollectedProxy(
        host="1.2.3.4",
        port=8080,
        protocol="http",
        country_code="US",
        source_last_checked=checked_at,
        metadata={"google": False},
    )

    snapshot = build_source_metadata(item)

    assert snapshot["country_code"] == "US"
    assert snapshot["source_last_checked"] == checked_at.isoformat()
    assert snapshot["google"] is False
