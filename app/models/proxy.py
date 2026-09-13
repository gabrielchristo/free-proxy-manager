import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ProxyStatus(str, enum.Enum):
    NEW = "NEW"
    CHECKING = "CHECKING"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DEAD = "DEAD"
    DISABLED = "DISABLED"


class ProxySource(Base):
    __tablename__ = "proxy_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    proxies_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    proxies: Mapped[list["ProxySourceLink"]] = relationship(back_populates="source")


class Proxy(Base):
    __tablename__ = "proxies"
    __table_args__ = (
        UniqueConstraint("protocol", "host", "port", name="uq_proxy_identity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    protocol: Mapped[str] = mapped_column(String(20), nullable=False)

    country: Mapped[str | None] = mapped_column(String(100))
    country_code: Mapped[str | None] = mapped_column(String(2))
    city: Mapped[str | None] = mapped_column(String(100))
    anonymity: Mapped[str | None] = mapped_column(String(50))
    isp: Mapped[str | None] = mapped_column(String(255))
    asn: Mapped[str | None] = mapped_column(String(50))
    org: Mapped[str | None] = mapped_column(String(255))
    ssl: Mapped[bool | None] = mapped_column(Boolean)
    source_latency_ms: Mapped[float | None] = mapped_column(Float)
    source_uptime_percent: Mapped[float | None] = mapped_column(Float)
    source_speed: Mapped[float | None] = mapped_column(Float)
    source_last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSON)

    status: Mapped[ProxyStatus] = mapped_column(
        Enum(ProxyStatus, native_enum=False, length=20),
        default=ProxyStatus.NEW,
        nullable=False,
    )

    latency_ms: Mapped[float | None] = mapped_column(Float)
    connect_time_ms: Mapped[float | None] = mapped_column(Float)
    last_http_status: Mapped[int | None] = mapped_column(Integer)

    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cooldown_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Sticky flag: set when the proxy first enters DEAD; used to deprioritize recheck.
    was_dead: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    sources: Mapped[list["ProxySourceLink"]] = relationship(back_populates="proxy")

    @property
    def url(self) -> str:
        return f"{self.protocol}://{self.host}:{self.port}"


class ProxySourceLink(Base):
    __tablename__ = "proxy_source_links"
    __table_args__ = (
        UniqueConstraint("proxy_id", "source_id", name="uq_proxy_source_link"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proxy_id: Mapped[int] = mapped_column(ForeignKey("proxies.id"), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("proxy_sources.id"), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source_metadata: Mapped[dict | None] = mapped_column(JSON)

    proxy: Mapped["Proxy"] = relationship(back_populates="sources")
    source: Mapped["ProxySource"] = relationship(back_populates="proxies")
