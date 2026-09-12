import logging

import httpx

from app.sources.base import CollectedProxy, ProxySourceBase

logger = logging.getLogger(__name__)

SUPPORTED_PROTOCOLS = {"http", "https"}


class ProxyScrapeSource(ProxySourceBase):
    name = "proxyscrape"

    def __init__(self, url: str, priority: int = 100) -> None:
        self.url = url
        self.priority = priority

    async def collect(self) -> list[CollectedProxy]:
        async with httpx.AsyncClient(timeout=30.0) as client:
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
            if protocol not in SUPPORTED_PROTOCOLS:
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

        logger.info("ProxyScrape collected %s HTTP/HTTPS proxies", len(proxies))
        return proxies
