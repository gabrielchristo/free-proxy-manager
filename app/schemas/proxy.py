from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProxyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    proxy: str
    protocol: str
    host: str
    port: int
    latency_ms: float | None = None
    score: float
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
    last_error: str | None = None
    metadata: dict | None = None
    status: str


class ProxyListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    proxy: str
    protocol: str
    host: str
    port: int
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
    last_error: str | None = None
    metadata: dict | None = None
    status: str
    latency_ms: float | None = None
    score: float
    success_count: int
    failure_count: int
    last_checked: datetime | None = None


class ProxyListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ProxyListItem]


class ProxyPoolStats(BaseModel):
    healthy: int
    degraded: int
    dead: int
    new: int
    checking: int
    disabled: int
    in_cooldown: int


class SourceStats(BaseModel):
    name: str
    enabled: bool
    proxies_found: int
    valid_proxies: int
    success_rate: float | None = None
    last_run: datetime | None = None
    last_success: datetime | None = None
    last_error: str | None = None


class StatsResponse(BaseModel):
    total_proxies: int
    pool: ProxyPoolStats
    http: int
    https: int
    average_latency: float | None = None
    success_rate: float | None = None
    proxies_by_country: dict[str, int] = Field(default_factory=dict)
    sources: list[SourceStats] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    database: str
    proxy_pool: ProxyPoolStats


class PoolSnapshotItem(BaseModel):
    recorded_at: datetime
    total_proxies: int
    pool: ProxyPoolStats


class PoolSnapshotHistoryResponse(BaseModel):
    hours: int
    count: int
    items: list[PoolSnapshotItem] = Field(default_factory=list)
