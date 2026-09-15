import logging
from urllib.parse import urlencode

import httpx

from app.sources.base import CollectedProxy, ProxySourceBase
from app.sources.proxyscrape import _parse_datetime, _parse_float

logger = logging.getLogger(__name__)

PROTOCOL_MAP = {
    "http": "http",
    "https": "https",
    "socks4": "socks4",
    "socks5": "socks5",
}

ANONYMITY_MAP = {
    "elite": "elite",
    "anonymous": "anonymous",
    "transparent": "transparent",
    "unknown": None,
}


class NodeMavenSource(ProxySourceBase):
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
                params = urlencode({"page": page, "per_page": self.page_size})
                response = await client.get(f"{self.url}?{params}")
                response.raise_for_status()
                payload = response.json()

                if not isinstance(payload, dict):
                    raise ValueError("NodeMaven payload must be a JSON object")

                rows = payload.get("proxies", [])
                if not isinstance(rows, list) or not rows:
                    break

                for item in rows:
                    if not isinstance(item, dict):
                        continue
                    parsed = self._parse_item(item, seen)
                    if parsed is not None:
                        proxies.append(parsed)

                total = int(payload.get("total") or 0)
                per_page = int(payload.get("per_page") or self.page_size)
                if page * per_page >= total:
                    break

        logger.info("%s collected %s supported proxies", self.name, len(proxies))
        return proxies

    def _parse_item(
        self,
        item: dict,
        seen: set[tuple[str, str, int]],
    ) -> CollectedProxy | None:
        protocol_raw = str(item.get("protocol", "")).lower().strip()
        protocol = PROTOCOL_MAP.get(protocol_raw)
        if protocol is None or protocol not in self.supported_protocols:
            return None

        host = str(item.get("ip_address", "")).strip()
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

        anonymity_raw = item.get("type")
        anonymity = None
        if anonymity_raw is not None:
            normalized = str(anonymity_raw).lower().strip()
            anonymity = ANONYMITY_MAP.get(normalized, normalized if normalized != "unknown" else None)

        latency_ms = _parse_float(item.get("latency"))

        return CollectedProxy(
            host=host,
            port=port,
            protocol=protocol,
            country=item.get("country"),
            anonymity=anonymity,
            source_latency_ms=latency_ms,
            source_last_checked=_parse_datetime(item.get("last_checked")),
            metadata={
                key: value
                for key, value in item.items()
                if key
                not in {
                    "ip_address",
                    "port",
                    "protocol",
                    "country",
                    "type",
                    "latency",
                    "last_checked",
                }
            }
            or None,
        )
