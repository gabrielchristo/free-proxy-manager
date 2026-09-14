import asyncio
import logging
import time
from contextlib import suppress

import httpx

from app.config import Settings, get_settings
from app.services.checker import CheckerService

logger = logging.getLogger(__name__)


class ConnectivityGuard:
    """Tracks direct internet reachability via a periodic background probe."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._checker = CheckerService(self.settings)
        self._client: httpx.AsyncClient | None = None
        self._available: bool | None = None
        self._checked_at: float = 0.0
        self._lock = asyncio.Lock()
        self._last_logged_state: bool | None = None
        self._probe_task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._client is not None:
            return
        timeout = httpx.Timeout(
            connect=self.settings.check_timeout,
            read=self.settings.check_timeout,
            write=self.settings.check_timeout,
            pool=self.settings.check_timeout,
        )
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=self.settings.check_follow_redirects,
            verify=True,
        )

        if not self.settings.connectivity_check_enabled:
            self._available = True
            return

        await self._refresh_state()
        self._probe_task = asyncio.create_task(
            self._probe_loop(),
            name="connectivity-probe-loop",
        )

    async def close(self) -> None:
        if self._probe_task is not None:
            self._probe_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._probe_task
            self._probe_task = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def is_available(self) -> bool:
        """Return the latest cached connectivity state (no HTTP probe)."""
        if not self.settings.connectivity_check_enabled:
            return True
        if self._available is None:
            return True
        return self._available

    async def _probe_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.connectivity_check_interval)
            await self._refresh_state()

    async def _refresh_state(self) -> None:
        async with self._lock:
            available = await self._probe()
            self._available = available
            self._checked_at = time.monotonic()
            self._log_state_change(available)

    async def _probe(self) -> bool:
        if self._client is None:
            await self.start()
        assert self._client is not None

        check_url = self._checker.validate_check_url()
        try:
            response = await self._client.get(check_url)
        except httpx.HTTPError as exc:
            logger.debug("Direct connectivity probe failed: %s", exc)
            return False

        return (
            self.settings.check_success_status_min
            <= response.status_code
            <= self.settings.check_success_status_max
        )

    def _log_state_change(self, available: bool) -> None:
        if self._last_logged_state == available:
            return
        if available:
            if self._last_logged_state is False:
                logger.info("Direct internet connectivity restored")
        else:
            logger.warning(
                "Direct internet connectivity lost — proxy checks paused "
                "to avoid false failures"
            )
        self._last_logged_state = available
