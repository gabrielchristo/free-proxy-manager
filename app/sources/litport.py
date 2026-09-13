import logging
from urllib.parse import urlencode

import httpx

from app.sources.base import CollectedProxy, ProxySourceBase
from app.sources.proxyscrape import _parse_datetime, _parse_float

logger = logging.getLogger(__name__)

ANONYMITY_MAP = {
    "elite": "elite",
    "high": "elite",
    "anonymous": "anonymous",
    "transparent": "transparent",
}


class LitportSource(ProxySourceBase):
    def __init__(
        self,
        name: str,
        url: str,
        priority: int,
        fetch_timeout: float,
        supported_protocols: frozenset[str],
        page_size: int = 500,
        max_pages: int = 10,
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
                        "page": page,
                        "limit": self.page_size,
                        "sortBy": "pingAt_desc",
                    }
                )
                response = await client.get(f"{self.url}?{params}")
                response.raise_for_status()
                payload = response.json()

                if not isinstance(payload, list) or not payload:
                    break

                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    parsed = self._parse_item(item, seen)
                    if parsed is not None:
                        proxies.append(parsed)

                if len(payload) < self.page_size:
                    break

        logger.info("%s collected %s supported proxies", self.name, len(proxies))
        return proxies

    def _parse_item(
        self,
        item: dict,
        seen: set[tuple[str, str, int]],
    ) -> CollectedProxy | None:
        protocol = str(item.get("protocol", "")).lower().strip()
        if protocol not in self.supported_protocols:
            return None

        host = str(item.get("host", "")).strip()
        port_raw = str(item.get("port", "")).strip()
        if not host or not port_raw:
            return None

        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            return None

        if not (1 <= port <= 65535):
            return None

        key = (protocol, host, port)
        if key in seen:
            return None
        seen.add(key)

        country_code = item.get("geoCountry")
        if country_code is not None:
            country_code = str(country_code).upper()[:2]

        anonymity_raw = item.get("anonymity")
        anonymity = None
        if anonymity_raw is not None:
            anonymity = ANONYMITY_MAP.get(str(anonymity_raw).lower(), str(anonymity_raw).lower())

        return CollectedProxy(
            host=host,
            port=port,
            protocol=protocol,
            country_code=country_code,
            city=item.get("geoCity"),
            anonymity=anonymity,
            isp=item.get("asnOrgName"),
            asn=item.get("asn"),
            ssl=item.get("https") if isinstance(item.get("https"), bool) else None,
            source_latency_ms=_parse_float(item.get("responseTimeMs")),
            source_uptime_percent=_parse_float(item.get("uptimeRating")),
            source_last_checked=_parse_datetime(item.get("pingAt")),
            metadata={
                key: value
                for key, value in item.items()
                if key
                not in {
                    "host",
                    "port",
                    "protocol",
                    "geoCountry",
                    "geoCity",
                    "anonymity",
                    "asnOrgName",
                    "asn",
                    "https",
                    "responseTimeMs",
                    "uptimeRating",
                    "pingAt",
                }
            }
            or None,
        )
