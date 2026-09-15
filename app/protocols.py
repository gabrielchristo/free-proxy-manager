"""Canonical proxy protocol helpers shared by collector, checker, and sources."""

from app.services.proxy_identity import normalize_host, prefer_protocol

HTTP_PROTOCOLS = frozenset({"http", "https"})
SOCKS_PROTOCOLS = frozenset({"socks4", "socks5"})
SUPPORTED_PROTOCOLS = HTTP_PROTOCOLS | SOCKS_PROTOCOLS


def normalize_protocol(protocol: str) -> str | None:
    """Return canonical protocol or None when unsupported."""
    cleaned = protocol.strip().lower()
    if cleaned in SUPPORTED_PROTOCOLS:
        return cleaned
    return None


def is_http_like(protocol: str) -> bool:
    return normalize_protocol(protocol) in HTTP_PROTOCOLS


def collection_batch_key(protocol: str, host: str, port: int) -> tuple[str, str, int] | None:
    """Key for in-batch deduplication during collection."""
    normalized = normalize_protocol(protocol)
    if normalized is None:
        return None

    endpoint_host = normalize_host(host)
    if not endpoint_host:
        return None

    if normalized in HTTP_PROTOCOLS:
        return ("http-like", endpoint_host, port)
    return (normalized, endpoint_host, port)


def merge_collected_protocol(existing: str, incoming: str) -> str:
    """Merge protocol labels for the same persisted endpoint."""
    existing_norm = normalize_protocol(existing)
    incoming_norm = normalize_protocol(incoming)
    if existing_norm is None:
        return incoming_norm or incoming.lower()
    if incoming_norm is None:
        return existing_norm
    if existing_norm in HTTP_PROTOCOLS and incoming_norm in HTTP_PROTOCOLS:
        return prefer_protocol(existing_norm, incoming_norm)
    return existing_norm
