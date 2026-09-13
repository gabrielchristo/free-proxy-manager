import logging
from urllib.parse import urlencode

import httpx

from app.sources.base import CollectedProxy, ProxySourceBase
from app.sources.proxyscrape import _parse_datetime, _parse_float

logger = logging.getLogger(__name__)


class GeonodeSource(ProxySourceBase):
    def __init__(
        self,
        name: str,
        url: str,
        priority: int,
        fetch_timeout: float,
        supported_protocols: frozenset[str],
        page_size: int = 100,
        max_pages: int = 25,
    ) -> None:
        self.name = name
        self.url = url.rstrip("/")
        self.priority = priority
        self.fetch_timeout = fetch_timeout
        self.supported_protocols = supported_protocols
        self.page_size = page_size
        self.max_pages = max_pages

    async def collect(self) -> list[CollectedProxy]:
        proxies: list[CollectedProxy] = []
        seen: set[tuple[str, str, int]] = set()

        async with httpx.AsyncClient(timeout=self.fetch_timeout) as client:
            for page in range(1, self.max_pages + 1):
                params = urlencode(
                    {
                        "limit": self.page_size,
                        "page": page,
                        "sort_by": "lastChecked",
                        "sort_type": "desc",
                    }
                )
                response = await client.get(f"{self.url}?{params}")
                response.raise_for_status()
                payload = response.json()

                rows = payload.get("data", [])
                if not isinstance(rows, list) or not rows:
                    break

                for item in rows:
                    if not isinstance(item, dict):
                        continue
                    proxies.extend(self._parse_item(item, seen))

                total = int(payload.get("total") or 0)
                if page * self.page_size >= total:
                    break

        logger.info("%s collected %s supported proxies", self.name, len(proxies))
        return proxies

    def _parse_item(
        self,
        item: dict,
        seen: set[tuple[str, str, int]],
    ) -> list[CollectedProxy]:
        host = str(item.get("ip", "")).strip()
        port_raw = item.get("port")
        if not host or port_raw is None:
            return []

        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            return []

        if not (1 <= port <= 65535):
            return []

        protocols = item.get("protocols") or []
        if isinstance(protocols, str):
            protocols = [protocols]

        country_code = item.get("country")
        if country_code is not None:
            country_code = str(country_code).upper()[:2]

        anonymity = item.get("anonymityLevel")
        if anonymity is not None:
            anonymity = str(anonymity).lower()

        collected: list[CollectedProxy] = []
        for protocol in protocols:
            protocol = str(protocol).lower().strip()
            if protocol not in self.supported_protocols:
                continue

            key = (protocol, host, port)
            if key in seen:
                continue
            seen.add(key)

            collected.append(
                CollectedProxy(
                    host=host,
                    port=port,
                    protocol=protocol,
                    country_code=country_code,
                    city=item.get("city"),
                    anonymity=anonymity,
                    isp=item.get("isp"),
                    asn=item.get("asn"),
                    org=item.get("org"),
                    source_latency_ms=_parse_float(item.get("latency")),
                    source_uptime_percent=_parse_float(item.get("upTime")),
                    source_speed=_parse_float(item.get("speed")),
                    source_last_checked=_parse_datetime(item.get("lastChecked")),
                    metadata={
                        key: value
                        for key, value in item.items()
                        if key
                        not in {
                            "ip",
                            "port",
                            "protocols",
                            "country",
                            "city",
                            "anonymityLevel",
                            "isp",
                            "asn",
                            "org",
                            "latency",
                            "upTime",
                            "speed",
                            "lastChecked",
                        }
                    }
                    or None,
                )
            )

        return collected
