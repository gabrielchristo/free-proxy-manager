from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.sources.proxyscrape import ProxyScrapeSource


@pytest.mark.asyncio
async def test_proxyscrape_parse_proxifly_geolocation():
    source = ProxyScrapeSource(
        name="proxifly-http",
        url="https://example.com/http.json",
        priority=75,
        fetch_timeout=30,
        supported_protocols=frozenset({"http"}),
    )

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = [
        {
            "proxy": "http://8.219.97.248:80",
            "protocol": "http",
            "ip": "8.219.97.248",
            "port": 80,
            "https": False,
            "anonymity": "transparent",
            "geolocation": {"country": "SG", "city": "Unknown"},
        }
    ]

    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.sources.proxyscrape.httpx.AsyncClient", return_value=client):
        proxies = await source.collect()

    assert len(proxies) == 1
    assert proxies[0].country_code == "SG"
    assert proxies[0].city == "Unknown"
