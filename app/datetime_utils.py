from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def format_log_datetime(value: datetime | None) -> str:
    if value is None:
        return "never"
    return as_utc(value).strftime("%Y-%m-%d %H:%M:%S")
