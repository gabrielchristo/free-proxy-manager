from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class SourceDefinition(BaseModel):
    name: str
    type: str
    enabled: bool = True
    url: str
    priority: int = Field(ge=0)
    protocol: str | None = None
    protocols: list[str] | None = None
    page_size: int | None = Field(default=None, ge=1, le=500)
    max_pages: int | None = Field(default=None, ge=1, le=500)
    fetch_timeout: float | None = Field(default=None, ge=1.0, le=120.0)

    @field_validator("protocol", "protocols", mode="before")
    @classmethod
    def normalize_protocol_fields(cls, value: object) -> object:
        if isinstance(value, str):
            return value.lower().strip()
        if isinstance(value, list):
            return [str(item).lower().strip() for item in value]
        return value


class SourcesConfig(BaseModel):
    fetch_timeout: float = Field(ge=1.0, le=120.0)
    sources: list[SourceDefinition]


def load_sources_config(path: Path) -> SourcesConfig:
    raw = path.read_text(encoding="utf-8")
    return SourcesConfig.model_validate_json(raw)
