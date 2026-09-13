import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CheckResult:
    success: bool
    latency_ms: float | None = None
    connect_time_ms: float | None = None
    http_status: int | None = None
    error: str | None = None
    requires_auth: bool = False


class PerRequestProxyTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        *,
        verify: bool | str = True,
        limits: httpx.Limits | None = None,
    ) -> None:
        self._verify = verify
        self._limits = limits or httpx.Limits(max_connections=1, max_keepalive_connections=0)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        proxy = request.extensions.get("proxy")
        if not proxy:
            raise RuntimeError("Missing proxy extension on checker request")

        transport = httpx.AsyncHTTPTransport(
            proxy=str(proxy),
            verify=self._verify,
            limits=self._limits,
        )
        try:
            return await transport.handle_async_request(request)
        finally:
            await transport.aclose()


class CheckerService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: httpx.AsyncClient | None = None
        self._timeout = httpx.Timeout(
            connect=self.settings.check_timeout,
            read=self.settings.check_timeout,
            write=self.settings.check_timeout,
            pool=self.settings.check_timeout,
        )

    async def start(self) -> None:
        if self._client is not None:
            return
        concurrency = self.settings.checker_concurrency
        transport = PerRequestProxyTransport(
            limits=httpx.Limits(
                max_connections=concurrency,
                max_keepalive_connections=0,
            ),
        )
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=self._timeout,
            follow_redirects=self.settings.check_follow_redirects,
            verify=True,
        )

    async def close(self) -> None:
        if self._client is None:
            return
        await self._client.aclose()
        self._client = None

    def validate_check_url(self, url: str | None = None) -> str:
        target = url or self.settings.check_url
        parsed = urlparse(target)
        if parsed.scheme not in self.settings.check_allowed_schemes:
            raise ValueError(f"Unsupported check URL scheme: {parsed.scheme}")
        if parsed.hostname not in self.settings.check_allowed_hosts:
            raise ValueError(
                f"Check URL host '{parsed.hostname}' is not in the allowlist"
            )
        return target

    async def check_proxy(
        self,
        host: str,
        port: int,
        protocol: str,
    ) -> CheckResult:
        check_url = self.validate_check_url()
        proxy_url = f"{protocol}://{host}:{port}"
        started = datetime.now(UTC)

        if self._client is None:
            async with httpx.AsyncClient(
                proxy=proxy_url,
                timeout=self._timeout,
                follow_redirects=self.settings.check_follow_redirects,
                verify=True,
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
