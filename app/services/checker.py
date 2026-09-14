import asyncio
import logging
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Normalized outcome of a single proxy HTTP probe."""

    success: bool
    latency_ms: float | None = None
    connect_time_ms: float | None = None
    http_status: int | None = None
    error: str | None = None
    requires_auth: bool = False


class ProxyTransportPool:
    """LRU cache of httpx proxy transports to avoid SSL stack churn per check."""

    def __init__(
        self,
        *,
        max_size: int,
        verify: bool | str = True,
        limits: httpx.Limits | None = None,
    ) -> None:
        self._max_size = max_size
        self._verify = verify
        self._limits = limits or httpx.Limits(max_connections=1, max_keepalive_connections=0)
        self._entries: OrderedDict[str, httpx.AsyncHTTPTransport] = OrderedDict()
        self._lock = asyncio.Lock()

    async def acquire(self, proxy_url: str) -> httpx.AsyncHTTPTransport:
        async with self._lock:
            cached = self._entries.get(proxy_url)
            if cached is not None:
                self._entries.move_to_end(proxy_url)
                return cached

            while len(self._entries) >= self._max_size:
                _, evicted = self._entries.popitem(last=False)
                await evicted.aclose()

            transport = httpx.AsyncHTTPTransport(
                proxy=proxy_url,
                verify=self._verify,
                limits=self._limits,
            )
            self._entries[proxy_url] = transport
            return transport

    async def close(self) -> None:
        async with self._lock:
            for transport in self._entries.values():
                await transport.aclose()
            self._entries.clear()


class PerRequestProxyTransport(httpx.AsyncBaseTransport):
    """Routes each request through a pooled proxy transport from request extensions."""

    def __init__(self, pool: ProxyTransportPool) -> None:
        self._pool = pool

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        proxy = request.extensions.get("proxy")
        if not proxy:
            raise RuntimeError("Missing proxy extension on checker request")

        transport = await self._pool.acquire(str(proxy))
        response = await transport.handle_async_request(request)
        # Buffer body before the caller closes the response; pooled transport stays open.
        await response.aread()
        return response


class CheckerService:
    """HTTP client wrapper that validates the probe URL and checks proxies."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: httpx.AsyncClient | None = None
        self._transport_pool: ProxyTransportPool | None = None
        self._timeout = httpx.Timeout(
            connect=self.settings.check_timeout,
            read=self.settings.check_timeout,
            write=self.settings.check_timeout,
            pool=self.settings.check_timeout,
        )

    async def start(self) -> None:
        """Create the shared AsyncClient used by checker workers."""
        if self._client is not None:
            return
        concurrency = self.settings.checker_concurrency
        self._transport_pool = ProxyTransportPool(
            max_size=self.settings.checker_transport_pool_size,
            verify=self.settings.check_ssl_verify,
            limits=httpx.Limits(
                max_connections=1,
                max_keepalive_connections=0,
            ),
        )
        transport = PerRequestProxyTransport(self._transport_pool)
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=self._timeout,
            follow_redirects=self.settings.check_follow_redirects,
            verify=self.settings.check_ssl_verify,
        )

    async def close(self) -> None:
        """Release the shared AsyncClient and pooled proxy transports."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        if self._transport_pool is not None:
            await self._transport_pool.close()
            self._transport_pool = None

    def validate_check_url(self, url: str | None = None) -> str:
        """Ensure the probe URL uses an allowed host and scheme."""
        target = url or self.settings.check_url
        parsed = urlparse(target)
        if parsed.scheme not in self.settings.check_allowed_schemes:
            raise ValueError(f"Unsupported check URL scheme: {parsed.scheme}")
        if parsed.hostname not in self.settings.check_allowed_hosts:
            raise ValueError(
                f"Check URL host '{parsed.hostname}' is not in the allowlist"
            )
        return target

    def proxy_connect_url(self, host: str, port: int, protocol: str) -> str:
        """Build the proxy URL used for HTTP checks."""
        connect_protocol = protocol.lower()
        if self.settings.check_https_proxy_as_http and connect_protocol == "https":
            connect_protocol = "http"
        return f"{connect_protocol}://{host}:{port}"

    async def check_proxy(
        self,
        host: str,
        port: int,
        protocol: str,
    ) -> CheckResult:
        """Probe one proxy against the configured check URL."""
        check_url = self.validate_check_url()
        proxy_url = self.proxy_connect_url(host, port, protocol)
        started = datetime.now(UTC)

        if self._client is None:
            async with httpx.AsyncClient(
                proxy=proxy_url,
                timeout=self._timeout,
                follow_redirects=self.settings.check_follow_redirects,
                verify=self.settings.check_ssl_verify,
            ) as client:
                return await self._perform_check(client, check_url, started)

        return await self._perform_check(
            self._client,
            check_url,
            started,
            proxy_url=proxy_url,
        )

    async def _perform_check(
        self,
        client: httpx.AsyncClient,
        check_url: str,
        started: datetime,
        proxy_url: str | None = None,
    ) -> CheckResult:
        """Execute GET through the proxy and map httpx errors to CheckResult."""
        request_kwargs: dict = {}
        if proxy_url is not None:
            request_kwargs["extensions"] = {"proxy": proxy_url}

        try:
            response = await client.get(check_url, **request_kwargs)
        except httpx.ProxyError as exc:
            message = str(exc)
            requires_auth = "407" in message or "authentication" in message.lower()
            return CheckResult(success=False, error=message, requires_auth=requires_auth)
        except httpx.TimeoutException:
            return CheckResult(success=False, error="timeout")
        except httpx.HTTPError as exc:
            return CheckResult(success=False, error=str(exc))

        elapsed_ms = (datetime.now(UTC) - started).total_seconds() * 1000
        requires_auth = response.status_code == 407
        success = (
            self.settings.check_success_status_min
            <= response.status_code
            <= self.settings.check_success_status_max
            and not requires_auth
        )

        return CheckResult(
            success=success,
            latency_ms=round(elapsed_ms, 2),
            connect_time_ms=round(elapsed_ms, 2),
            http_status=response.status_code,
            error=None if success else f"HTTP {response.status_code}",
            requires_auth=requires_auth,
        )
