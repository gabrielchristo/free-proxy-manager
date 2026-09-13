import json

from app.sources.proxycompass import PROXYLISTER_AJAX_PATTERN, ProxyCompassSource


def test_proxycompass_parse_item_infers_https_from_port():
    source = ProxyCompassSource(
        name="proxycompass",
        url="https://proxycompass.com/?page_id=455912",
        priority=80,
        fetch_timeout=30,
        supported_protocols=frozenset({"http", "https"}),
    )
    seen: set[tuple[str, str, int]] = set()

    item = source._parse_item({"ip_address": "1.2.3.4", "port": 443}, seen)

    assert item is not None
    assert item.protocol == "https"
    assert item.host == "1.2.3.4"


def test_proxycompass_parse_item_defaults_to_http():
    source = ProxyCompassSource(
        name="proxycompass",
        url="https://proxycompass.com/?page_id=455912",
        priority=80,
        fetch_timeout=30,
        supported_protocols=frozenset({"http", "https"}),
    )
    seen: set[tuple[str, str, int]] = set()

    item = source._parse_item({"ip_address": "1.2.3.4", "port": 8080}, seen)

    assert item is not None
    assert item.protocol == "http"


def test_proxycompass_extracts_nonce_from_page_snippet():
    html = '<script id="proxylister-js-js-extra">var proxylister_ajax = {"ajax_url":"https://proxycompass.com/wp-admin/admin-ajax.php","nonce":"abc123"};</script>'
    match = PROXYLISTER_AJAX_PATTERN.search(html)
    assert match is not None
    payload = json.loads(match.group(1))
    assert payload["nonce"] == "abc123"
