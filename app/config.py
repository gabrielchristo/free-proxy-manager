from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "free-proxy-manager"
    database_url: str = "sqlite:///./data/proxies.db"

    checker_concurrency: int = Field(default=50, ge=1, le=500)
    check_timeout: float = Field(default=5.0, ge=1.0, le=60.0)
    check_url: str = "https://www.google.com/"

    collect_interval: int = Field(default=900, ge=60)
    recheck_interval: int = Field(default=300, ge=60)
    cleanup_interval: int = Field(default=3600, ge=300)
    score_interval: int = Field(default=300, ge=60)

    failure_threshold: int = Field(default=3, ge=1)
    cooldown_initial: int = Field(default=300, ge=60)
    cooldown_max: int = Field(default=7200, ge=300)

    proxyscrape_url: str = (
        "https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/all/data.json"
    )
    proxyscrape_enabled: bool = True
    proxyscrape_priority: int = 100

    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    pool_min_score: float = Field(default=10.0, ge=0.0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
