from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CollectedProxy:
    host: str
    port: int
    protocol: str
    country: str | None = None
    country_code: str | None = None
    anonymity: str | None = None


class ProxySourceBase:
    name: str
    url: str
    priority: int = 100

    async def collect(self) -> list[CollectedProxy]:
        raise NotImplementedError
