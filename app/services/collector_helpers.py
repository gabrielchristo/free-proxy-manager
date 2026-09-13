from datetime import datetime

from app.models import Proxy
from app.sources.base import CollectedProxy


def merge_metadata(existing: dict | None, incoming: dict | None) -> dict | None:
    if not incoming:
        return existing
    merged = dict(existing or {})
    merged.update(incoming)
    return merged


def apply_collected_fields(proxy: Proxy, item: CollectedProxy) -> None:
    scalar_fields = (
        "country",
        "country_code",
        "city",
        "anonymity",
        "isp",
        "asn",
        "org",
        "ssl",
        "source_latency_ms",
        "source_uptime_percent",
        "source_speed",
        "source_last_checked",
    )
    for field_name in scalar_fields:
        value = getattr(item, field_name)
        if value is not None:
            setattr(proxy, field_name, value)

    proxy.metadata_json = merge_metadata(proxy.metadata_json, item.metadata)


def build_source_metadata(item: CollectedProxy) -> dict:
    snapshot = item.source_snapshot()
    if item.metadata:
        for key, value in item.metadata.items():
            if key not in snapshot:
                snapshot[key] = _serialize_metadata_value(value)
    return snapshot


def _serialize_metadata_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    return value
