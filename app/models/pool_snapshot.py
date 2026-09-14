from datetime import datetime

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PoolSnapshot(Base):
    """Point-in-time counts of proxy pool status for trend charts."""

    __tablename__ = "pool_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    total_proxies: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    healthy: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    degraded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dead: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checking: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    disabled: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    in_cooldown: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
