from app.sources.proxydb import ProxyDbSource

SAMPLE_ROW = """
<tr><td><a href="/190.58.248.86/80#http" title="example">190.58.248.86</a></td>
<td><a href="/190.58.248.86/80#http">80</a></td>
<td>HTTP</td>
<td><abbr title="Trinidad and Tobago">TT</abbr></td>
<td><span class="text-success">High Anonymous</span></td>
<td><span class="text-success">100.00%</span></td>
<td><span class="text-success">0.8s</span></td>
<td><span class="text-muted">–</span></td>
<td><span>1d ago</span></td></tr>
"""


def test_proxydb_parse_page_extracts_row_metadata():
    source = ProxyDbSource(
        name="proxydb",
        url="https://proxydb.net/",
        priority=60,
        fetch_timeout=30,
        supported_protocols=frozenset({"http", "https"}),
    )
    seen: set[tuple[str, str, int]] = set()

    collected = source._parse_page(SAMPLE_ROW, seen)

    assert len(collected) == 1
    proxy = collected[0]
    assert proxy.host == "190.58.248.86"
    assert proxy.port == 80
    assert proxy.protocol == "http"
    assert proxy.country_code == "TT"
    assert proxy.anonymity == "elite"
    assert proxy.source_uptime_percent == 100.0
    assert proxy.source_latency_ms == 800.0


def test_proxydb_parse_page_skips_socks5():
    source = ProxyDbSource(
        name="proxydb",
        url="https://proxydb.net/",
        priority=60,
        fetch_timeout=30,
        supported_protocols=frozenset({"http"}),
    )
    seen: set[tuple[str, str, int]] = set()
    html = SAMPLE_ROW.replace("#http", "#socks5").replace("HTTP", "SOCKS5")

    assert source._parse_page(html, seen) == []
