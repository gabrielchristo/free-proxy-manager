import json
import logging
import re
from urllib.parse import urljoin, urlparse

import httpx

from app.sources.base import CollectedProxy, ProxySourceBase

logger = logging.getLogger(__name__)

PROXYLISTER_AJAX_PATTERN = re.compile(
    r"var\s+proxylister_ajax\s*=\s*(\{.*?\});",
    re.DOTALL,
)
HTTPS_PORTS = frozenset({443, 8443, 10443})


class ProxyCompassSource(ProxySourceBase):
    def __init__(
        self,
        name: str,
        url: str,
        priority: int,
        fetch_timeout: float,
        supported_protocols: frozenset[str],
        download_url: str | None = None,
        export_filter: dict | None = None,
    ) -> None:
        self.name = name
        self.url = url
        self.priority = priority
        self.fetch_timeout = fetch_timeout
        self.supported_protocols = supported_protocols
        self.export_filter = export_filter or {}
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        self.download_url = download_url or urljoin(origin, "/wp-admin/admin-ajax.php")

    async def collect(self) -> list[CollectedProxy]:
        async with httpx.AsyncClient(
            timeout=self.fetch_timeout,
            follow_redirects=True,
            headers={"User-Agent": "free-proxy-manager/1.0"},
        ) as client:
            nonce = await self._fetch_nonce(client)
            response = await client.get(
                self.download_url,
                params={
                    "action": "proxylister_download",
                    "nonce": nonce,
                    "format": "json",
                    "filter": json.dumps(self.export_filter, separators=(",", ":")),
                },
            )
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, list):
            raise ValueError("ProxyCompass payload must be a JSON array")

        proxies: list[CollectedProxy] = []
        seen: set[tuple[str, str, int]] = set()
        for item in payload:
            if not isinstance(item, dict):
                continue
            parsed = self._parse_item(item, seen)
            if parsed is not None:
                proxies.append(parsed)

        logger.info("%s collected %s supported proxies", self.name, len(proxies))
        return proxies

    async def _fetch_nonce(self, client: httpx.AsyncClient) -> str:
        response = await client.get(self.url)
        response.raise_for_status()
        match = PROXYLISTER_AJAX_PATTERN.search(response.text)
        if not match:
            raise ValueError("ProxyCompass proxylister nonce not found in page HTML")
        payload = json.loads(match.group(1))
        nonce = payload.get("nonce")
        if not nonce:
            raise ValueError("ProxyCompass proxylister nonce missing from page config")
        return str(nonce)

    def _parse_item(
        self,
        item: dict,
        seen: set[tuple[str, str, int]],
    ) -> CollectedProxy | None:
        host = str(item.get("ip_address") or item.get("ip") or "").strip()
        port_raw = item.get("port")
        if not host or port_raw is None:
            return None

        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            return None

        if not (1 <= port <= 65535):
            return None

        protocol = self._infer_protocol(item, port)
        if protocol is None:
            return None

        key = (protocol, host, port)
        if key in seen:
            return None
        seen.add(key)

        return CollectedProxy(
            host=host,
            port=port,
            protocol=protocol,
            metadata={
                "source_record": item,
                "source_export": "proxylister_download",
            },
        )

    def _infer_protocol(self, item: dict, port: int) -> str | None:
        raw_protocol = item.get("protocol") or item.get("protocols")
        if isinstance(raw_protocol, list):
            for candidate in raw_protocol:
                protocol = str(candidate).lower().strip()
                if protocol in self.supported_protocols:
                    return protocol
        elif raw_protocol:
            protocol = str(raw_protocol).lower().strip()
            if protocol in self.supported_protocols:
                return protocol

        if port in HTTPS_PORTS and "https" in self.supported_protocols:
            return "https"
        if "http" in self.supported_protocols:
            return "http"
        if "https" in self.supported_protocols:
            return "https"
        return None


def infer_protocol_from_port(port: int, supported_protocols: frozenset[str]) -> str | None:
    if port in HTTPS_PORTS and "https" in supported_protocols:
        return "https"
    if "http" in supported_protocols:
        return "http"
    if "https" in supported_protocols:
        return "https"
    return None
