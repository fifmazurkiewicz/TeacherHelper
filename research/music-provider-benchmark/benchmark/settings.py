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

    kie_api_key: str | None = None
    kie_api_base_url: str = "https://api.kie.ai"
    kie_music_callback_url: str | None = None
    kie_music_poll_interval_seconds: float = 1.0

    wavespeed_api_key: str | None = None
    wavespeed_api_base_url: str = "https://api.wavespeed.ai"

    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str | None = None

    elevenlabs_api_key: str | None = None
    elevenlabs_api_base_url: str = "https://api.elevenlabs.io"

    benchmark_secret: str | None = Field(default=None, validation_alias="BENCHMARK_SECRET")


def get_settings() -> Settings:
    return Settings()
