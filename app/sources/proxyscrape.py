import logging

import httpx

from app.config import Settings, get_settings
from app.sources.base import CollectedProxy, ProxySourceBase

logger = logging.getLogger(__name__)


class ProxyScrapeSource(ProxySourceBase):
    def __init__(
        self,
        name: str,
        url: str,
        priority: int,
        fetch_timeout: float,
        supported_protocols: frozenset[str],
    ) -> None:
        self.name = name
        self.url = url
        self.priority = priority
        self.fetch_timeout = fetch_timeout
        self.supported_protocols = supported_protocols

    async def collect(self) -> list[CollectedProxy]:
        async with httpx.AsyncClient(timeout=self.fetch_timeout) as client:
            response = await client.get(self.url)
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, list):
            raise ValueError("ProxyScrape payload must be a JSON array")

        proxies: list[CollectedProxy] = []
        for item in payload:
            if not isinstance(item, dict):
                continue

            protocol = str(item.get("protocol", "")).lower().strip()
            if protocol not in self.supported_protocols:
                continue

            host = str(item.get("ip", "")).strip()
            port = item.get("port")
            if not host or port is None:
                continue

            try:
                port_int = int(port)
            except (TypeError, ValueError):
                continue

            if not (1 <= port_int <= 65535):
                continue

            proxies.append(
                CollectedProxy(
                    host=host,
                    port=port_int,
                    protocol=protocol,
                    country=item.get("country"),
                    country_code=item.get("country_code"),
                    anonymity=item.get("anonymity"),
                )
            )

        logger.info("%s collected %s supported proxies", self.name, len(proxies))
        return proxies
