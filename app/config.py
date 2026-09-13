from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str
    database_url: str
    log_level: str
    log_format: str
    log_color_enabled: bool
    api_host: str
    api_port: int = Field(ge=1, le=65535)

    checker_concurrency: int = Field(ge=1, le=500)
    check_timeout: float = Field(ge=1.0, le=60.0)
    check_url: str
    check_allowed_hosts: Annotated[frozenset[str], NoDecode]
    check_allowed_schemes: Annotated[frozenset[str], NoDecode]
    check_success_status_min: int = Field(ge=100, le=599)
    check_success_status_max: int = Field(ge=100, le=599)
    check_follow_redirects: bool

    collect_interval: int = Field(ge=60)
    recheck_interval: int = Field(ge=60)
    cleanup_interval: int = Field(ge=300)
    score_interval: int = Field(ge=60)
    recheck_batch_size: int = Field(ge=1)

    failure_threshold: int = Field(ge=1)
    cooldown_initial: int = Field(ge=60)
    cooldown_max: int = Field(ge=300)
    cooldown_max_level: int = Field(ge=1)

    pool_min_score: float = Field(ge=0.0)
    pool_top_candidates: int = Field(ge=1)
    pool_selection_min_weight: float = Field(ge=0.1)

    api_default_limit: int = Field(ge=1)
    api_max_limit: int = Field(ge=1)
    api_max_score: float = Field(ge=0.0, le=100.0)

    cleanup_stale_days: int = Field(ge=1)

    db_pool_size: int = Field(ge=1)
    db_pool_max_overflow: int = Field(ge=0)
    db_pool_timeout: int = Field(ge=1)
    db_sqlite_timeout: int = Field(ge=1)
    db_wal_autocheckpoint: int = Field(ge=0)
    db_checkpoint_on_commit: bool
    db_checkpoint_commit_mode: str
    db_checkpoint_interval: int = Field(ge=0)
    db_checkpoint_interval_mode: str

    sources_config_path: str

    anonymous_exclude_value: str

    scorer_success_weight: float = Field(ge=0.0)
    scorer_latency_max: float = Field(ge=0.0)
    scorer_latency_divisor: float = Field(ge=1.0)
    scorer_recency_max: float = Field(ge=0.0)
    scorer_failure_penalty: float = Field(ge=0.0)
    scorer_history_cap: int = Field(ge=0)
    scorer_score_max: float = Field(ge=1.0)
    scorer_https_bonus: float = Field(ge=0.0)
    scorer_https_protocol: str
    scorer_multi_source_bonus: float = Field(ge=0.0)
    scorer_anonymity_bonus: Annotated[dict[str, float], NoDecode]

    @field_validator("scorer_anonymity_bonus", mode="before")
    @classmethod
    def parse_scorer_anonymity_bonus(cls, value: object) -> dict[str, float]:
        if isinstance(value, dict):
            return {str(key).strip().lower(): float(bonus) for key, bonus in value.items()}
        if isinstance(value, str):
            bonuses: dict[str, float] = {}
            for entry in value.split(","):
                item = entry.strip()
                if not item:
                    continue
                if "=" not in item:
                    raise ValueError(f"Invalid SCORER_ANONYMITY_BONUS entry: {item}")
                level, raw_bonus = item.split("=", 1)
                level = level.strip().lower()
                if not level:
                    raise ValueError(f"Invalid SCORER_ANONYMITY_BONUS entry: {item}")
                bonuses[level] = float(raw_bonus.strip())
            return bonuses
        raise TypeError("SCORER_ANONYMITY_BONUS must be a comma-separated key=value list")

    @field_validator("db_checkpoint_commit_mode", "db_checkpoint_interval_mode")
    @classmethod
    def validate_checkpoint_mode(cls, value: str) -> str:
        normalized = value.strip().upper()
        allowed = {"PASSIVE", "FULL", "RESTART", "TRUNCATE"}
        if normalized not in allowed:
            raise ValueError(f"Checkpoint mode must be one of {sorted(allowed)}")
        return normalized

    @field_validator(
        "check_allowed_hosts",
        "check_allowed_schemes",
        mode="before",
    )
    @classmethod
    def parse_csv_set(cls, value: object) -> frozenset[str]:
        if isinstance(value, frozenset):
            return value
        if isinstance(value, (set, list, tuple)):
            return frozenset(str(item).strip() for item in value if str(item).strip())
        if isinstance(value, str):
            return frozenset(item.strip() for item in value.split(",") if item.strip())
        raise TypeError("Expected comma-separated string or collection")


@lru_cache
def get_settings() -> Settings:
    return Settings()
