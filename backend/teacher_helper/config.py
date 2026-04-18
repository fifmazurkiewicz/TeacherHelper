from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Katalog główny repozytorium (…/TeacherHelper/.env), niezależnie od cwd przy starcie uvicorn.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ROOT_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "TeacherHelper API"
    debug: bool = False
    # Swagger / Redoc — domyślnie włączone (lokalnie); na produkcji ustaw OPENAPI_DOCS=false
    openapi_docs: bool = True

    # --- Baza danych ---
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/teacher"
    database_url_sync: str = "postgresql+psycopg://postgres:postgres@localhost:5432/teacher"

    # --- JWT ---
    jwt_secret: str = "change-me-in-production-use-openssl-rand"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 168

    # --- Storage plików ---
    storage_root: Path = Path("data/storage")

    # --- OpenRouter (jeden klucz, trzy modele) ---
    openrouter_api_key: str | None = None
    openrouter_model: str = "google/gemini-3.1-flash-lite-preview"
    openrouter_module_model: str = "google/gemini-3-flash-preview"
    openrouter_image_model: str = "google/gemini-3.1-flash-image-preview"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str | None = None

    # --- Embeddingi (OpenAI) ---
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    # --- DALL-E (fallback obrazów gdy brak OpenRouter) ---
    dalle_api_key: str | None = None
    dalle_model: str = "dall-e-3"

    # --- KIE.ai (generacja muzyki — POST /api/v1/generate) ---
    kie_api_key: str | None = None
    kie_api_base_url: str = "https://api.kie.ai"
    kie_music_model: str = "V4_5ALL"
    # Wymagane przez wiele konfiguracji KIE — URL webhooka po zakończeniu generacji.
    kie_music_callback_url: str | None = None
    # True = customMode (style, title, dłuższy prompt); False = tryb uproszczony z dokumentacji (tylko prompt ≤ 500).
    kie_music_custom_mode: bool = True
    # Polling GET /api/v1/generate/record-info po taskId (0 = wyłączony). Max ~3 żądania/s na task wg dokumentacji.
    kie_music_poll_timeout_seconds: int = 120
    kie_music_poll_interval_seconds: float = 1.0
    kie_music_instrumental_default: bool = True
    kie_music_negative_tags: str | None = None
    kie_music_vocal_gender: str | None = None  # "m" | "f"
    kie_music_style_weight: float | None = None
    kie_music_weirdness_constraint: float | None = None
    kie_music_audio_weight: float | None = None
    kie_music_persona_id: str | None = None
    kie_music_persona_model: str | None = None
    # Opcjonalnie: klucz HMAC z https://kie.ai/settings — wtedy webhook weryfikuje X-Webhook-Signature.
    kie_webhook_hmac_key: str | None = None

    # --- Qdrant ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "file_chunks"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Admin ---
    admin_api_key: str | None = None
    default_rate_limit_rpm: int = 100

    # --- Limity tokenów ---
    llm_daily_token_soft_limit: int | None = None
    llm_daily_token_hard_limit: int | None = None

    # --- Operacje destrukcyjne ---
    require_resource_confirmation: bool = True
    confirmation_token_expire_minutes: int = 15

    # --- Opcjonalne: Langfuse ---
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # --- CORS ---
    cors_origins: str = "*"

    # --- Opcjonalne: Alerty webhook ---
    alert_webhook_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
