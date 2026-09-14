import ipaddress
import re

_IPV4_PATTERN = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def normalize_host(host: str) -> str:
    """Normalize host for deduplication (canonical IP or lowercase hostname)."""
    cleaned = host.strip()
    if not cleaned:
        return cleaned

    if _IPV4_PATTERN.match(cleaned):
        parts = cleaned.split(".")
        if len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
            return ".".join(str(int(part)) for part in parts)

    try:
        return str(ipaddress.ip_address(cleaned))
    except ValueError:
        return cleaned.lower().rstrip(".")


def proxy_identity(host: str, port: int) -> tuple[str, int]:
    return normalize_host(host), port


def prefer_protocol(existing: str, incoming: str) -> str:
    """Prefer HTTPS when the same host:port appears under multiple protocols."""
    rank = {"https": 2, "http": 1}
    existing_rank = rank.get(existing.lower(), 0)
    incoming_rank = rank.get(incoming.lower(), 0)
    if incoming_rank > existing_rank:
        return incoming.lower()
    return existing.lower()
