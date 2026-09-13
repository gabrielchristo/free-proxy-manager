from app.sources.text_list import normalize_source_url, parse_text_list


def test_normalize_github_blob_url_to_raw():
    blob_url = (
        "https://github.com/iplocate/free-proxy-list/blob/main/protocols/http.txt"
    )
    assert normalize_source_url(blob_url) == (
        "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/http.txt"
    )


def test_parse_text_list_skips_comments_and_invalid_lines():
    body = "1.2.3.4:8080\n\n# comment\n5.6.7.8:3128\ninvalid-line\n"
    proxies = parse_text_list(body, "https")

    assert len(proxies) == 2
    assert proxies[0].host == "1.2.3.4"
    assert proxies[0].port == 8080
    assert proxies[0].protocol == "https"
    assert proxies[1].host == "5.6.7.8"
    assert proxies[1].port == 3128
