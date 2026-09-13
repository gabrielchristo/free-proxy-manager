import logging
from datetime import UTC, datetime

import httpx

from app.sources.base import CollectedProxy, ProxySourceBase

logger = logging.getLogger(__name__)


def _parse_epoch_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return _parse_epoch_timestamp(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    return None


def _parse_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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

            metadata = {
                key: value
                for key, value in item.items()
                if key not in {"ip", "port", "protocol"}
            }

            proxies.append(
                CollectedProxy(
                    host=host,
                    port=port_int,
                    protocol=protocol,
                    country=item.get("country"),
                    country_code=item.get("country_code"),
                    city=item.get("city"),
                    anonymity=item.get("anonymity"),
                    isp=item.get("isp"),
                    asn=item.get("asn"),
                    ssl=_parse_bool(item.get("ssl")),
                    source_latency_ms=_parse_float(item.get("latency_ms")),
                    source_uptime_percent=_parse_float(item.get("uptime_percent")),
                    source_last_checked=_parse_datetime(item.get("last_checked")),
                    metadata=metadata or None,
                )
            )

        logger.info("%s collected %s supported proxies", self.name, len(proxies))
        return proxies
