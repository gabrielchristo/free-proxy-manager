from app.sources.nodemaven import NodeMavenSource


def test_nodemaven_parse_item_maps_https_protocol():
    source = NodeMavenSource(
        name="nodemaven",
        url="https://freeproxies.nodemaven.com/proxies",
        priority=65,
        fetch_timeout=30,
        supported_protocols=frozenset({"http", "https"}),
    )
    seen: set[tuple[str, str, int]] = set()

    collected = source._parse_item(
        {
            "ip_address": "96.126.113.216",
            "port": "59166",
            "protocol": "HTTPS",
            "country": "United States",
            "type": "Anonymous",
            "latency": "4102",
            "last_checked": "Sun, 13 Sep 2026 07:37:56 GMT",
        },
        seen,
    )

    assert collected is not None
    assert collected.protocol == "https"
    assert collected.port == 59166
    assert collected.anonymity == "anonymous"
    assert collected.source_latency_ms == 4102.0


def test_nodemaven_parse_item_skips_socks():
    source = NodeMavenSource(
        name="nodemaven",
        url="https://freeproxies.nodemaven.com/proxies",
        priority=65,
        fetch_timeout=30,
        supported_protocols=frozenset({"https"}),
    )
    seen: set[tuple[str, str, int]] = set()

    assert (
        source._parse_item(
            {"ip_address": "1.2.3.4", "port": "8080", "protocol": "SOCKS5"},
            seen,
        )
        is None
    )
