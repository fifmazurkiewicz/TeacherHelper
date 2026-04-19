from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str | None = None
    openai_api_base_url: str = "https://api.openai.com"

    stability_api_key: str | None = None
    stability_api_base_url: str = "https://api.stability.ai"

    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str | None = None

    benchmark_secret: str | None = Field(default=None, validation_alias="BENCHMARK_SECRET")


def get_settings() -> Settings:
    return Settings()
