import logging
from pathlib import Path

from app.config import Settings, get_settings
from app.sources.base import ProxySourceBase
from app.sources.config import SourcesConfig, load_sources_config
from app.sources.proxyscrape import ProxyScrapeSource
from app.sources.text_list import TextListSource

logger = logging.getLogger(__name__)


def resolve_sources_config_path(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    path = Path(settings.sources_config_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def load_sources(settings: Settings | None = None) -> list[ProxySourceBase]:
    settings = settings or get_settings()
    config_path = resolve_sources_config_path(settings)
    config = load_sources_config(config_path)
    sources = build_sources(config)
    logger.info(
        "Loaded %s proxy sources from %s",
        len(sources),
        config_path,
    )
    return sources


def build_sources(config: SourcesConfig) -> list[ProxySourceBase]:
    built: list[ProxySourceBase] = []

    for item in config.sources:
        if not item.enabled:
            logger.info("[source-config] Skipping disabled source %s", item.name)
            continue

        fetch_timeout = item.fetch_timeout or config.fetch_timeout

        if item.type == "proxyscrape":
            if not item.protocols:
                raise ValueError(f"Source {item.name} requires protocols")
            built.append(
                ProxyScrapeSource(
                    name=item.name,
                    url=item.url,
                    priority=item.priority,
                    fetch_timeout=fetch_timeout,
                    supported_protocols=frozenset(item.protocols),
                )
            )
            continue

        if item.type == "text_list":
            if not item.protocol:
                raise ValueError(f"Source {item.name} requires protocol")
            built.append(
                TextListSource(
                    name=item.name,
                    url=item.url,
                    protocol=item.protocol,
                    priority=item.priority,
                    fetch_timeout=fetch_timeout,
                )
            )
            continue

        raise ValueError(f"Unsupported source type: {item.type}")

    return built
