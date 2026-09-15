import asyncio
import logging
from datetime import UTC, datetime
from urllib.parse import urlparse

from socksio import socks4, socks5

from app.protocols import normalize_protocol
from app.services.checker import CheckResult

logger = logging.getLogger(__name__)


def _ensure_socksio() -> None:
    try:
        import socksio  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "SOCKS proxy checks require socksio. Install with: pip install socksio"
        ) from exc


async def check_socks_proxy(
    *,
    protocol: str,
    proxy_host: str,
    proxy_port: int,
    check_url: str,
    timeout: float,
    success_status_min: int,
    success_status_max: int,
) -> CheckResult:
    """Probe a SOCKS4 or SOCKS5 proxy with a raw HTTP GET through the tunnel."""
    _ensure_socksio()
    protocol_norm = normalize_protocol(protocol)
    if protocol_norm not in {"socks4", "socks5"}:
        return CheckResult(success=False, error=f"unsupported socks protocol: {protocol}")

    parsed = urlparse(check_url)
    if not parsed.hostname:
        return CheckResult(success=False, error="invalid check URL")

    dest_port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if parsed.scheme == "https":
        return CheckResult(
            success=False,
            error="HTTPS check URL is not supported for socks checks",
        )

    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    request_line = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {parsed.hostname}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode()

    try:
        return await asyncio.wait_for(
            _perform_socks_probe(
                protocol=protocol_norm,
                proxy_host=proxy_host,
                proxy_port=proxy_port,
                dest_host=parsed.hostname,
                dest_port=dest_port,
                request_line=request_line,
                started=datetime.now(UTC),
                success_status_min=success_status_min,
                success_status_max=success_status_max,
            ),
            timeout=timeout,
        )
    except TimeoutError:
        return CheckResult(success=False, error="timeout")
    except OSError as exc:
        return CheckResult(success=False, error=str(exc))
    except Exception as exc:
        logger.debug(
            "SOCKS check failed for %s:%s (%s): %s",
            proxy_host,
            proxy_port,
            protocol_norm,
            exc,
        )
        return CheckResult(success=False, error=str(exc))


async def check_socks4_proxy(
    *,
    proxy_host: str,
    proxy_port: int,
    check_url: str,
    timeout: float,
    success_status_min: int,
    success_status_max: int,
) -> CheckResult:
    return await check_socks_proxy(
        protocol="socks4",
        proxy_host=proxy_host,
        proxy_port=proxy_port,
        check_url=check_url,
        timeout=timeout,
        success_status_min=success_status_min,
        success_status_max=success_status_max,
    )


async def check_socks5_proxy(
    *,
    proxy_host: str,
    proxy_port: int,
    check_url: str,
    timeout: float,
    success_status_min: int,
    success_status_max: int,
) -> CheckResult:
    return await check_socks_proxy(
        protocol="socks5",
        proxy_host=proxy_host,
        proxy_port=proxy_port,
        check_url=check_url,
        timeout=timeout,
        success_status_min=success_status_min,
        success_status_max=success_status_max,
    )


async def _perform_socks_probe(
    *,
    protocol: str,
    proxy_host: str,
    proxy_port: int,
    dest_host: str,
    dest_port: int,
    request_line: bytes,
    started: datetime,
    success_status_min: int,
    success_status_max: int,
) -> CheckResult:
    reader, writer = await asyncio.open_connection(proxy_host, proxy_port)
    try:
        if protocol == "socks4":
            tunnel_error = await _establish_socks4_tunnel(
                reader,
                writer,
                dest_host=dest_host,
                dest_port=dest_port,
            )
        else:
            tunnel_error = await _establish_socks5_tunnel(
                reader,
                writer,
                dest_host=dest_host,
                dest_port=dest_port,
            )
        if tunnel_error is not None:
            return tunnel_error

        writer.write(request_line)
        await writer.drain()

        raw = await _read_http_response(reader)
        if not raw:
            return CheckResult(success=False, error="empty HTTP response")

        status_code = _parse_http_status(raw)
        elapsed_ms = (datetime.now(UTC) - started).total_seconds() * 1000
        if status_code is None:
            return CheckResult(
                success=False,
                latency_ms=round(elapsed_ms, 2),
                error="invalid HTTP response",
            )

        success = success_status_min <= status_code <= success_status_max
        return CheckResult(
            success=success,
            latency_ms=round(elapsed_ms, 2),
            connect_time_ms=round(elapsed_ms, 2),
            http_status=status_code,
            error=None if success else f"HTTP {status_code}",
        )
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def _establish_socks4_tunnel(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    dest_host: str,
    dest_port: int,
) -> CheckResult | None:
    conn = socks4.SOCKS4Connection(user_id=b"")
    request = socks4.SOCKS4ARequest.from_address(
        socks4.SOCKS4Command.CONNECT,
        f"{dest_host}:{dest_port}",
    )
    conn.send(request)
    writer.write(conn.data_to_send())
    await writer.drain()

    reply_data = await reader.read(4096)
    if not reply_data:
        return CheckResult(success=False, error="empty SOCKS4 reply")

    reply = conn.receive_data(reply_data)
    if reply.reply_code != socks4.SOCKS4ReplyCode.REQUEST_GRANTED:
        return CheckResult(
            success=False,
            error=f"SOCKS4 rejected: {reply.reply_code.name.lower()}",
        )
    return None


async def _establish_socks5_tunnel(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    dest_host: str,
    dest_port: int,
) -> CheckResult | None:
    conn = socks5.SOCKS5Connection()
    conn.send(
        socks5.SOCKS5AuthMethodsRequest([socks5.SOCKS5AuthMethod.NO_AUTH_REQUIRED])
    )
    writer.write(conn.data_to_send())
    await writer.drain()

    auth_data = await reader.read(4096)
    if not auth_data:
        return CheckResult(success=False, error="empty SOCKS5 auth reply")

    auth_reply = conn.receive_data(auth_data)
    if not isinstance(auth_reply, socks5.SOCKS5AuthReply):
        return CheckResult(success=False, error="invalid SOCKS5 auth reply")

    if auth_reply.method == socks5.SOCKS5AuthMethod.NO_ACCEPTABLE_METHODS:
        return CheckResult(success=False, error="SOCKS5 rejected auth methods")

    if auth_reply.method == socks5.SOCKS5AuthMethod.USERNAME_PASSWORD:
        return CheckResult(
            success=False,
            error="SOCKS5 authentication required",
            requires_auth=True,
        )

    if auth_reply.method != socks5.SOCKS5AuthMethod.NO_AUTH_REQUIRED:
        return CheckResult(
            success=False,
            error=f"unsupported SOCKS5 auth method: {auth_reply.method!r}",
        )

    conn.send(
        socks5.SOCKS5CommandRequest.from_address(
            socks5.SOCKS5Command.CONNECT,
            f"{dest_host}:{dest_port}",
        )
    )
    writer.write(conn.data_to_send())
    await writer.drain()

    connect_data = await reader.read(4096)
    if not connect_data:
        return CheckResult(success=False, error="empty SOCKS5 connect reply")

    connect_reply = conn.receive_data(connect_data)
    if not isinstance(connect_reply, socks5.SOCKS5Reply):
        return CheckResult(success=False, error="invalid SOCKS5 connect reply")

    if connect_reply.reply_code != socks5.SOCKS5ReplyCode.SUCCEEDED:
        return CheckResult(
            success=False,
            error=f"SOCKS5 rejected: {connect_reply.reply_code.name.lower()}",
        )
    return None


async def _read_http_response(reader: asyncio.StreamReader) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await reader.read(4096)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > 65536:
            break
    return b"".join(chunks)


def _parse_http_status(raw: bytes) -> int | None:
    line = raw.split(b"\r\n", 1)[0]
    parts = line.split()
    if len(parts) < 2:
        return None
    if parts[0].startswith(b"HTTP/"):
        try:
            return int(parts[1])
        except ValueError:
            return None
    return None
