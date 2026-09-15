from app.protocols import (
    collection_batch_key,
    merge_collected_protocol,
    normalize_protocol,
)
from app.services.proxy_identity import prefer_protocol


def test_normalize_protocol_accepts_socks():
    assert normalize_protocol("SOCKS5") == "socks5"
    assert normalize_protocol("socks4") == "socks4"
    assert normalize_protocol("ftp") is None


def test_collection_batch_key_merges_http_family():
    assert collection_batch_key("http", "10.0.0.1", 8080) == (
        "http-like",
        "10.0.0.1",
        8080,
    )
    assert collection_batch_key("https", "10.0.0.1", 8080) == (
        "http-like",
        "10.0.0.1",
        8080,
    )
    assert collection_batch_key("socks5", "10.0.0.1", 8080) == (
        "socks5",
        "10.0.0.1",
        8080,
    )


def test_merge_collected_protocol_prefers_https_within_http_family():
    assert merge_collected_protocol("http", "https") == "https"
    assert merge_collected_protocol("https", "http") == "https"
    assert merge_collected_protocol("socks5", "socks5") == "socks5"
    assert merge_collected_protocol("socks4", "socks5") == "socks4"


def test_prefer_protocol_still_used_for_http_https():
    assert prefer_protocol("http", "https") == "https"
