from app.sources.litport import LitportSource


def test_litport_parse_item_normalizes_port_and_metadata():
    source = LitportSource(
        name="litport",
        url="https://litport.net/api/free-proxy",
        priority=70,
        fetch_timeout=30,
        supported_protocols=frozenset({"http", "https"}),
    )
    seen: set[tuple[str, str, int]] = set()

    collected = source._parse_item(
        {
            "protocol": "http",
            "host": "203.19.38.114",
            "port": "1080\r",
            "geoCountry": "HK",
            "geoCity": "Tung Chung",
            "anonymity": "elite",
            "responseTimeMs": 1177,
            "uptimeRating": 99,
            "pingAt": "2026-09-13T08:51:06.069Z",
        },
        seen,
    )

    assert collected is not None
    assert collected.host == "203.19.38.114"
    assert collected.port == 1080
    assert collected.country_code == "HK"
    assert collected.anonymity == "elite"
    assert collected.source_latency_ms == 1177.0


def test_litport_parse_item_skips_socks():
    source = LitportSource(
        name="litport",
        url="https://litport.net/api/free-proxy",
        priority=70,
        fetch_timeout=30,
        supported_protocols=frozenset({"http", "https"}),
    )
    seen: set[tuple[str, str, int]] = set()

    assert source._parse_item({"protocol": "socks4", "host": "1.2.3.4", "port": "8080"}, seen) is None
