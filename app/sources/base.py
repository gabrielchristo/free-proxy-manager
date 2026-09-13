from dataclasses import dataclass, fields
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CollectedProxy:
    host: str
    port: int
    protocol: str
    country: str | None = None
    country_code: str | None = None
    city: str | None = None
    anonymity: str | None = None
    isp: str | None = None
    asn: str | None = None
    org: str | None = None
    ssl: bool | None = None
    source_latency_ms: float | None = None
    source_uptime_percent: float | None = None
    source_speed: float | None = None
    source_last_checked: datetime | None = None
    metadata: dict | None = None

    def source_snapshot(self) -> dict:
        snapshot: dict = {}
        for field in fields(self):
            value = getattr(self, field.name)
            if value is None:
                continue
            if field.name == "metadata" and isinstance(value, dict):
                snapshot.update(value)
            elif isinstance(value, datetime):
                snapshot[field.name] = value.isoformat()
            else:
                snapshot[field.name] = value
        return snapshot


class ProxySourceBase:
    name: str
    url: str
    priority: int

    async def collect(self) -> list[CollectedProxy]:
        raise NotImplementedError
