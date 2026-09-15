from unittest.mock import AsyncMock, patch

import pytest

from app.services.checker import CheckerService


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", ["socks4", "socks5"])
async def test_check_proxy_routes_socks_to_custom_checker(protocol: str):
    service = CheckerService()
    expected = AsyncMock()
    expected.success = True
    expected.latency_ms = 42.0

    with patch(
        "app.services.socks_checker.check_socks_proxy",
        new_callable=AsyncMock,
        return_value=expected,
    ) as mock_socks:
        result = await service.check_proxy("91.107.163.185", 9098, protocol)

    mock_socks.assert_awaited_once_with(
        protocol=protocol,
        proxy_host="91.107.163.185",
        proxy_port=9098,
        check_url=service.validate_check_url(),
        timeout=service.settings.check_timeout,
        success_status_min=service.settings.check_success_status_min,
        success_status_max=service.settings.check_success_status_max,
    )
    assert result is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", ["socks4", "socks5"])
async def test_check_proxy_socks_does_not_use_httpx_transport_pool(protocol: str):
    service = CheckerService()
    await service.start()

    try:
        with patch(
            "app.services.socks_checker.check_socks_proxy",
            new_callable=AsyncMock,
            return_value=AsyncMock(success=False, error="mock"),
        ) as mock_socks:
            with patch.object(service, "_perform_check", new_callable=AsyncMock) as mock_http:
                await service.check_proxy("91.107.163.185", 9098, protocol)

        mock_socks.assert_awaited_once()
        mock_http.assert_not_awaited()
    finally:
        await service.close()
