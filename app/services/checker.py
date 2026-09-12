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


class CheckerService:
    ALLOWED_HOSTS = {"www.google.com", "google.com"}

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def validate_check_url(self, url: str | None = None) -> str:
        target = url or self.settings.check_url
        parsed = urlparse(target)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"Unsupported check URL scheme: {parsed.scheme}")
        if parsed.hostname not in self.ALLOWED_HOSTS:
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
        timeout = httpx.Timeout(
            connect=self.settings.check_timeout,
            read=self.settings.check_timeout,
            write=self.settings.check_timeout,
            pool=self.settings.check_timeout,
        )

        started = datetime.now(UTC)
        try:
            async with httpx.AsyncClient(
                proxy=proxy_url,
                timeout=timeout,
                follow_redirects=True,
                verify=True,
            ) as client:
                response = await client.get(check_url)
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
        success = 200 <= response.status_code < 400 and not requires_auth

        return CheckResult(
            success=success,
            latency_ms=round(elapsed_ms, 2),
            connect_time_ms=round(elapsed_ms, 2),
            http_status=response.status_code,
            error=None if success else f"HTTP {response.status_code}",
            requires_auth=requires_auth,
        )
