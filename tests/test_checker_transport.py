from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.checker import PerRequestProxyTransport, ProxyTransportPool


@pytest.mark.asyncio
async def test_per_request_proxy_transport_surfaces_connect_error_not_read_error():
    """Regression: closing inner transport before body read caused ReadError on every check."""
    pool = ProxyTransportPool(max_size=4)
    transport = PerRequestProxyTransport(pool)

    try:
        async with httpx.AsyncClient(
            transport=transport,
            timeout=2,
            follow_redirects=True,
        ) as client:
            with pytest.raises(httpx.ConnectError):
                await client.get(
                    "http://detectportal.firefox.com/success.txt",
                    extensions={"proxy": "http://127.0.0.1:1"},
                )
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_proxy_transport_pool_reuses_cached_transport():
    pool = ProxyTransportPool(max_size=4)
    created: list[httpx.AsyncHTTPTransport] = []
    original = httpx.AsyncHTTPTransport

    def factory(*args, **kwargs):
        transport = original(*args, **kwargs)
        created.append(transport)
        return transport

    with patch("app.services.checker.httpx.AsyncHTTPTransport", side_effect=factory):
        first = await pool.acquire("http://1.2.3.4:8080")
        second = await pool.acquire("http://1.2.3.4:8080")

    assert first is second
    assert len(created) == 1
    await pool.close()


@pytest.mark.asyncio
async def test_proxy_transport_pool_evicts_oldest_when_full():
    pool = ProxyTransportPool(max_size=2)
    created: list[httpx.AsyncHTTPTransport] = []
    original = httpx.AsyncHTTPTransport

    def factory(*args, **kwargs):
        transport = original(*args, **kwargs)
        created.append(transport)
        return transport

    with patch("app.services.checker.httpx.AsyncHTTPTransport", side_effect=factory):
        await pool.acquire("http://1.1.1.1:80")
        await pool.acquire("http://2.2.2.2:80")
        await pool.acquire("http://3.3.3.3:80")

    assert len(created) == 3
    assert len(pool._entries) == 2
    assert "http://1.1.1.1:80" not in pool._entries
    await pool.close()
