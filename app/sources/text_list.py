import logging
import re

import httpx

from app.sources.base import CollectedProxy, ProxySourceBase

logger = logging.getLogger(__name__)

LINE_PATTERN = re.compile(
    r"^(?P<host>[0-9a-zA-Z.\-]+):(?P<port>\d+)\s*(?:#.*)?$"
)


def normalize_source_url(url: str) -> str:
    if "github.com" in url and "/blob/" in url:
        return (
            url.replace("https://github.com/", "https://raw.githubusercontent.com/")
            .replace("/blob/", "/")
        )
    return url


def parse_text_list(body: str, protocol: str) -> list[CollectedProxy]:
    proxies: list[CollectedProxy] = []
    seen: set[tuple[str, int]] = set()

    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        match = LINE_PATTERN.match(line)
        if match is None:
            continue

        host = match.group("host")
        try:
            port = int(match.group("port"))
        except ValueError:
            continue

        if not (1 <= port <= 65535):
            continue

        key = (host, port)
        if key in seen:
            continue
        seen.add(key)

        proxies.append(
            CollectedProxy(
                host=host,
                port=port,
                protocol=protocol,
            )
        )

    return proxies


class TextListSource(ProxySourceBase):
    def __init__(
        self,
        name: str,
        url: str,
        protocol: str,
        priority: int,
        fetch_timeout: float,
    ) -> None:
        self.name = name
        self.url = normalize_source_url(url)
        self.protocol = protocol
        self.priority = priority
        self.fetch_timeout = fetch_timeout

    async def collect(self) -> list[CollectedProxy]:
        async with httpx.AsyncClient(timeout=self.fetch_timeout) as client:
            response = await client.get(self.url)
            response.raise_for_status()
            body = response.text

        proxies = parse_text_list(body, self.protocol)
        logger.info("%s collected %s %s proxies", self.name, len(proxies), self.protocol)
        return proxies
