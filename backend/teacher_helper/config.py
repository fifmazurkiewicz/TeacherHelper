from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator
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

    # --- xAI (Grok) — transkrypcja mowy STT w Asystencie (POST /v1/voice/transcribe → api.x.ai/v1/stt) ---
    xai_api_key: str | None = None
    xai_base_url: str = "https://api.x.ai/v1"

    # --- OpenRouter: jeden OPENROUTER_API_KEY, modele wybierasz osobno (zmienne .env w nawiasach) ---
    openrouter_api_key: str | None = None
    # OPENROUTER_MODEL — główny czat / orchestrator
    openrouter_model: str = Field(default="google/gemini-3.1-flash-lite-preview")
    # OPENROUTER_MODULE_MODEL — wywołania LLM w modułach (scenariusz, tekst piosenki itd.)
    openrouter_module_model: str = Field(default="google/gemini-3-flash-preview")
    # OPENROUTER_IMAGE_MODEL — generacja obrazów wyłącznie przez OpenRouter (modalities image).
    # Domyślnie Nano Banana 2: google/gemini-3.1-flash-image-preview.
    # Nano Banana (Gemini 2.5 Flash Image): google/gemini-2.5-flash-image
    openrouter_image_model: str = Field(default="google/gemini-3.1-flash-image-preview")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str | None = None
    # Limit długości uzupełnienia (max_tokens); zapobiega ucięciu długich opracowań w modułach.
    openrouter_max_completion_tokens: int | None = Field(default=8192, ge=256)
    openrouter_module_max_completion_tokens: int | None = Field(default=16384, ge=512)
    # Muzyka (Lyria): OPENROUTER_MUSIC_ENABLED, OPENROUTER_MUSIC_MODEL, OPENROUTER_MUSIC_TIMEOUT_SECONDS
    openrouter_music_enabled: bool = Field(default=True)
    openrouter_music_model: str = Field(default="google/lyria-3-pro-preview")
    openrouter_music_timeout_seconds: float = Field(default=300.0)
    # Ile osobnych utworów zlecać każdemu dostawcy (KIE + Lyria) przy jednym generate_music (max 5).
    music_variants_per_provider: int = 2
    # Generacja obrazów (OpenRouter chat/completions + modalities); tylko gdy OPENROUTER_API_KEY.
    openrouter_image_timeout_seconds: float = Field(default=120.0)
    # Opcjonalnie: image_config.image_size dla modeli Gemini Image (np. 1K, 2K); puste = nie wysyłaj.
    openrouter_image_size: str | None = Field(default="1K")

    # --- Embeddingi: OpenAI (bezpośrednio) albo OpenRouter (/v1/embeddings); patrz EMBEDDINGS_BACKEND ---
    embeddings_backend: Literal["auto", "openai", "openrouter"] = "auto"
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    openrouter_embedding_model: str = "openai/text-embedding-3-small"
    embedding_dim: int = 1536

    # --- DALL-E (nieużywane — grafika wyłącznie przez OpenRouter; pola zostają dla starych .env) ---
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
    # Gdy użytkownik nie ma własnego llm_daily_token_limit w bazie — stosowany limit dzienny (UTC) na czat.
    default_user_llm_daily_token_limit: int = Field(default=25000, ge=1, le=2_000_000_000)

    # --- Kontekst rozmowy (zwijanie długich wątków) ---
    chat_summary_enabled: bool = Field(default=True)
    # Ile ostatnich tur (para user+asystent) trzymać dosłownie w kontekście modelu.
    chat_summary_recent_turns: int = Field(default=14, ge=2, le=80)
    # Szacunek znaków surowej historii — powyżej próbujemy zwinąć starszą część w podsumowanie.
    chat_context_max_chars: int = Field(default=45000, ge=8000, le=500000)
    # Maks. liczba wiadomości (user+assistant) przekazywana do orchestratora po ewentualnym skrócie.
    chat_orchestrator_max_messages: int = Field(default=36, ge=8, le=200)
    # Osobne wywołanie LLM do skrótu — domyślnie ten sam model co orchestrator; można ustawić tańszy.
    openrouter_summary_model: str | None = None
    openrouter_summary_max_completion_tokens: int | None = Field(default=2048, ge=256)

    # --- Operacje destrukcyjne ---
    require_resource_confirmation: bool = True
    confirmation_token_expire_minutes: int = 15

    # --- Tavily — wyszukiwanie w internecie (narzędzie search_web w asystencie) ---
    tavily_api_key: str | None = None
    web_search_max_results: int = Field(default=5, ge=1, le=15)

    # --- Opcjonalne: Langfuse ---
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # --- CORS ---
    cors_origins: str = "*"

    # --- Replicate — generowanie efektów dźwiękowych (POST /v1/sound/generate) ---
    replicate_api_key: str | None = None
    # Model w formacie "owner/name" (np. meta/musicgen); musi obsługiwać parametry musicgen.
    replicate_sound_model: str = "meta/musicgen"
    # Wariant modelu musicgen: stereo-large | large | melody | stereo-melody-large
    replicate_sound_musicgen_version: str = "stereo-large"
    # Format wyjściowy: mp3 | wav
    replicate_sound_output_format: str = "mp3"
    # Czas oczekiwania na zakończenie predykcji (polling).
    replicate_sound_timeout_seconds: float = Field(default=120.0)
    replicate_sound_poll_interval_seconds: float = Field(default=2.0)
    # Pojedyncze wywołanie MusicGen — typowo maks. 30 s (model meta/musicgen na Replicate).
    replicate_sound_max_duration_seconds: int = Field(default=30, ge=1, le=30)

    # --- Opcjonalne: Alerty webhook ---
    alert_webhook_url: str | None = None

    @model_validator(mode="after")
    def _strip_secret_strings(self) -> Self:
        for name in (
            "xai_api_key",
            "openrouter_api_key",
            "openai_api_key",
            "dalle_api_key",
            "kie_api_key",
            "qdrant_api_key",
            "admin_api_key",
            "langfuse_public_key",
            "langfuse_secret_key",
            "kie_webhook_hmac_key",
            "tavily_api_key",
            "replicate_api_key",
        ):
            val = getattr(self, name)
            if isinstance(val, str):
                s = val.strip()
                setattr(self, name, s or None)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
