from app.sources.geonode import GeonodeSource


def test_geonode_parse_item_expands_supported_protocols():
    source = GeonodeSource(
        name="geonode",
        url="https://proxylist.geonode.com/api/proxy-list",
        priority=85,
        fetch_timeout=30,
        supported_protocols=frozenset({"http", "https"}),
    )
    seen: set[tuple[str, str, int]] = set()

    collected = source._parse_item(
        {
            "ip": "1.2.3.4",
            "port": "8080",
            "protocols": ["http", "https"],
            "country": "br",
            "anonymityLevel": "elite",
        },
        seen,
    )

    assert len(collected) == 2
    assert {item.protocol for item in collected} == {"http", "https"}
    assert all(item.host == "1.2.3.4" and item.port == 8080 for item in collected)
    assert all(item.country_code == "BR" and item.anonymity == "elite" for item in collected)


def test_geonode_parse_item_skips_unsupported_protocols():
    source = GeonodeSource(
        name="geonode",
        url="https://proxylist.geonode.com/api/proxy-list",
        priority=85,
        fetch_timeout=30,
        supported_protocols=frozenset({"http"}),
    )
    seen: set[tuple[str, str, int]] = set()

    collected = source._parse_item(
        {"ip": "1.2.3.4", "port": 3128, "protocols": ["socks4", "http"]},
        seen,
    )

    assert len(collected) == 1
    assert collected[0].protocol == "http"
