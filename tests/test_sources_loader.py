from app.sources.config import SourcesConfig
from app.sources.loader import build_sources


def test_build_sources_from_json_config():
    config = SourcesConfig.model_validate(
        {
            "fetch_timeout": 15,
            "sources": [
                {
                    "name": "proxyscrape",
                    "type": "proxyscrape",
                    "enabled": True,
                    "url": "https://example.com/list.json",
                    "priority": 100,
                    "protocols": ["http", "https"],
                },
                {
                    "name": "iplocate-http",
                    "type": "text_list",
                    "enabled": False,
                    "url": "https://example.com/http.txt",
                    "protocol": "http",
                    "priority": 90,
                },
                {
                    "name": "geonode",
                    "type": "geonode",
                    "enabled": True,
                    "url": "https://proxylist.geonode.com/api/proxy-list",
                    "priority": 85,
                    "protocols": ["http", "https"],
                    "page_size": 50,
                    "max_pages": 10,
                },
            ],
        }
    )

    sources = build_sources(config)

    assert len(sources) == 2
    assert sources[0].name == "proxyscrape"
    assert sources[0].priority == 100
    assert sources[1].name == "geonode"
    assert sources[1].page_size == 50
    assert sources[1].max_pages == 10
