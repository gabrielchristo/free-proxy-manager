from datetime import UTC, datetime

from app.models import Proxy, ProxyStatus
from app.services.pool import PoolService


def test_get_best_proxy_respects_filters(db_session):
    db_session.add_all(
        [
            Proxy(
                host="10.0.0.1",
                port=8080,
                protocol="http",
                country_code="BR",
                status=ProxyStatus.HEALTHY,
                score=90,
                latency_ms=100,
                last_seen=datetime.now(UTC),
            ),
            Proxy(
                host="10.0.0.2",
                port=8080,
                protocol="http",
                country_code="US",
                status=ProxyStatus.HEALTHY,
                score=95,
                latency_ms=80,
                last_seen=datetime.now(UTC),
            ),
        ]
    )
    db_session.commit()

    service = PoolService()
    proxy = service.get_best_proxy(db_session, country_code="BR")
    assert proxy is not None
    assert proxy.country_code == "BR"


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["database"] == "ok"
    assert "proxy_pool" in payload
