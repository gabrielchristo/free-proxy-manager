import logging
import re
from urllib.parse import urlencode, urljoin, urlparse

import httpx

from app.sources.base import CollectedProxy, ProxySourceBase
from app.sources.proxyscrape import _parse_float

logger = logging.getLogger(__name__)

ROW_BLOCK_PATTERN = re.compile(
    r'<tr><td><a href="/(?P<host>[\d.]+)/(?P<port>\d+)#(?P<protocol>\w+)"[\s\S]*?</tr>',
    re.IGNORECASE,
)
COUNTRY_CODE_PATTERN = re.compile(
    r'<abbr[^>]*>(?P<country>[A-Z]{2})</abbr>',
    re.IGNORECASE,
)
ANONYMITY_PATTERN = re.compile(
    r'>(?P<anonymity>Transparent|Anonymous|High Anonymous)</span>',
    re.IGNORECASE,
)
UPTIME_PATTERN = re.compile(r'>(?P<uptime>[\d.]+%)</span>')
RESPONSE_TIME_PATTERN = re.compile(r'>(?P<response_time>[\d.]+s)</span>')

ANONYMITY_MAP = {
    "high anonymous": "elite",
    "anonymous": "anonymous",
    "transparent": "transparent",
}

PROTOCOL_MAP = {
    "http": "http",
    "https": "https",
}


class ProxyDbSource(ProxySourceBase):
    def __init__(
        self,
        name: str,
        url: str,
        priority: int,
        fetch_timeout: float,
        supported_protocols: frozenset[str],
        max_pages: int = 20,
    ) -> None:
        self.name = name
        self.url = url.rstrip("/") or "/"
        self.priority = priority
        self.fetch_timeout = fetch_timeout
        self.supported_protocols = supported_protocols
        self.max_pages = max_pages
        parsed = urlparse(url if "://" in url else f"https://proxydb.net{url}")
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        self.list_path = parsed.path or "/"

    async def collect(self) -> list[CollectedProxy]:
        proxies: list[CollectedProxy] = []
        seen: set[tuple[str, str, int]] = set()
        page_size = 30

        async with httpx.AsyncClient(
            timeout=self.fetch_timeout,
            follow_redirects=True,
            headers={"User-Agent": "free-proxy-manager/1.0"},
        ) as client:
            for page_index in range(self.max_pages):
                offset = page_index * page_size
                params = urlencode(
                    [
                        ("protocol", protocol)
                        for protocol in sorted(self.supported_protocols)
                    ]
                    + [("offset", offset)]
                )
                page_url = urljoin(self.origin, self.list_path)
                response = await client.get(f"{page_url}?{params}")
                response.raise_for_status()
                page_proxies = self._parse_page(response.text, seen)
                if not page_proxies:
                    break
                proxies.extend(page_proxies)

        logger.info("%s collected %s supported proxies", self.name, len(proxies))
        return proxies

    def _parse_page(
        self,
        html: str,
        seen: set[tuple[str, str, int]],
    ) -> list[CollectedProxy]:
        proxies: list[CollectedProxy] = []

        for match in ROW_BLOCK_PATTERN.finditer(html):
            protocol = PROTOCOL_MAP.get(match.group("protocol").lower())
            if protocol is None or protocol not in self.supported_protocols:
                continue

            host = match.group("host")
            try:
                port = int(match.group("port"))
            except ValueError:
                continue

            if not (1 <= port <= 65535):
                continue

            key = (protocol, host, port)
            if key in seen:
                continue
            seen.add(key)

            block = match.group(0)
            country_match = COUNTRY_CODE_PATTERN.search(block)
            anonymity_match = ANONYMITY_PATTERN.search(block)
            uptime_match = UPTIME_PATTERN.search(block)
            response_time_match = RESPONSE_TIME_PATTERN.search(block)

            anonymity = None
            if anonymity_match:
                anonymity = ANONYMITY_MAP.get(anonymity_match.group("anonymity").lower())

            source_uptime_percent = None
            if uptime_match:
                source_uptime_percent = _parse_float(uptime_match.group("uptime").rstrip("%"))

            source_latency_ms = None
            if response_time_match:
                seconds = _parse_float(response_time_match.group("response_time").rstrip("s"))
                if seconds is not None:
                    source_latency_ms = seconds * 1000

            proxies.append(
                CollectedProxy(
                    host=host,
                    port=port,
                    protocol=protocol,
                    country_code=country_match.group("country") if country_match else None,
                    anonymity=anonymity,
                    source_uptime_percent=source_uptime_percent,
                    source_latency_ms=source_latency_ms,
                )
            )

        return proxies
