import httpx
import pytest

from app.services.checker import PerRequestProxyTransport


@pytest.mark.asyncio
async def test_per_request_proxy_transport_surfaces_connect_error_not_read_error():
    """Regression: closing inner transport before body read caused ReadError on every check."""
    transport = PerRequestProxyTransport()

    async with httpx.AsyncClient(
        transport=transport,
        timeout=2,
        follow_redirects=True,
    ) as client:
        with pytest.raises(httpx.ConnectError):
            await client.get(
                "https://www.google.com/",
                extensions={"proxy": "http://127.0.0.1:1"},
            )
