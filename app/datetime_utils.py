from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current UTC timestamp with timezone info."""
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Normalize naive datetimes to UTC-aware values."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def format_log_datetime(value: datetime | None) -> str:
    """Format timestamps for logs using 24h UTC (YYYY-MM-DD HH:MM:SS)."""
    if value is None:
        return "never"
    return as_utc(value).strftime("%Y-%m-%d %H:%M:%S")
