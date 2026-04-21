"""Fabryki adapterów — LLM, generatory obrazów/wideo.

Jeden plik z przejrzystym fallbackiem:
  OpenRouter (klucz) → Stub (bez kluczy)
"""
from __future__ import annotations

from teacher_helper.config import get_settings
from teacher_helper.use_cases.ports import (
    ImageGeneratorPort,
    LlmClientPort,
    MusicGeneratorPort,
    SoundGeneratorPort,
    VideoGeneratorPort,
)


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

def _build_openrouter(model: str, *, max_completion_tokens: int | None) -> LlmClientPort:
    from teacher_helper.infrastructure.llm_openrouter import OpenRouterLlmClient

    s = get_settings()
    return OpenRouterLlmClient(
        api_key=s.openrouter_api_key,  # type: ignore[arg-type]
        model=model,
        base_url=s.openrouter_base_url,
        http_referer=s.openrouter_http_referer,
        app_title=s.app_name,
        max_completion_tokens=max_completion_tokens,
    )


def _build_llm(model_attr: str, *, max_completion_tokens: int | None) -> LlmClientPort:
    from teacher_helper.infrastructure.llm_stub import StubLlmClient

    s = get_settings()
    if s.openrouter_api_key:
        return _build_openrouter(getattr(s, model_attr), max_completion_tokens=max_completion_tokens)
    return StubLlmClient()


def build_llm_client() -> LlmClientPort:
    """LLM do orchestracji (tani, szybki)."""
    s = get_settings()
    return _build_llm("openrouter_model", max_completion_tokens=s.openrouter_max_completion_tokens)


def build_module_llm_client() -> LlmClientPort:
    """LLM do modułów (reasoning, lepszy model)."""
    s = get_settings()
    return _build_llm("openrouter_module_model", max_completion_tokens=s.openrouter_module_max_completion_tokens)


def build_summary_llm_client() -> LlmClientPort:
    """LLM do skracania historii rozmowy (podsumowanie zwijanej części wątku)."""
    s = get_settings()
    model = (s.openrouter_summary_model or "").strip() or s.openrouter_model
    if s.openrouter_api_key:
        return _build_openrouter(model, max_completion_tokens=s.openrouter_summary_max_completion_tokens)
    from teacher_helper.infrastructure.llm_stub import StubLlmClient

    return StubLlmClient()


# ---------------------------------------------------------------------------
# Generatory mediów
# ---------------------------------------------------------------------------

def build_image_generator() -> ImageGeneratorPort | None:
    """Grafika wyłącznie przez OpenRouter (chat/completions + modalities image)."""
    s = get_settings()
    key = (s.openrouter_api_key or "").strip()
    model = (s.openrouter_image_model or "").strip()
    if not key or not model:
        return None
    from teacher_helper.infrastructure.image_openrouter import OpenRouterImageGenerator

    img_size = (s.openrouter_image_size or "").strip() or None
    return OpenRouterImageGenerator(
        api_key=key,
        model=model,
        base_url=s.openrouter_base_url,
        http_referer=s.openrouter_http_referer,
        app_title=s.app_name,
        timeout=float(s.openrouter_image_timeout_seconds or 120.0),
        image_size=img_size,
    )


def build_video_generator() -> VideoGeneratorPort | None:
    """Brak produkcyjnych adapterów — fallback na storyboard JSON."""
    return None


def build_music_generator() -> MusicGeneratorPort | None:
    """KIE.ai gdy ustawiony ``KIE_API_KEY`` — inaczej tylko plik TXT z promptem od LLM."""
    s = get_settings()
    if not (s.kie_api_key or "").strip():
        return None
    from teacher_helper.infrastructure.music_kie import KieMusicGenerator

    return KieMusicGenerator(
        api_key=s.kie_api_key.strip(),  # type: ignore[arg-type]
        base_url=s.kie_api_base_url,
        default_callback_url=(s.kie_music_callback_url or "").strip() or None,
        default_negative_tags=(s.kie_music_negative_tags or "").strip() or None,
        default_vocal_gender=(s.kie_music_vocal_gender or "").strip() or None,
        default_style_weight=s.kie_music_style_weight,
        default_weirdness_constraint=s.kie_music_weirdness_constraint,
        default_audio_weight=s.kie_music_audio_weight,
        default_persona_id=(s.kie_music_persona_id or "").strip() or None,
        default_persona_model=(s.kie_music_persona_model or "").strip() or None,
    )


def build_sound_generator() -> SoundGeneratorPort | None:
    """Replicate sound effects — ``None`` gdy brak ``REPLICATE_API_KEY``."""
    s = get_settings()
    if not (s.replicate_api_key or "").strip():
        return None
    from teacher_helper.infrastructure.replicate_sound import ReplicateSoundGenerator

    return ReplicateSoundGenerator(
        api_key=s.replicate_api_key.strip(),  # type: ignore[arg-type]
        model=s.replicate_sound_model,
        musicgen_model_version=s.replicate_sound_musicgen_version,
        output_format=s.replicate_sound_output_format,
        timeout=s.replicate_sound_timeout_seconds,
        poll_interval=s.replicate_sound_poll_interval_seconds,
    )


def build_lyria_music_generator():
    """Lyria przez OpenRouter — ``None`` gdy brak klucza lub wyłączone w konfiguracji."""
    s = get_settings()
    if not s.openrouter_music_enabled:
        return None
    if not (s.openrouter_api_key or "").strip():
        return None
    from teacher_helper.infrastructure.lyria_openrouter import OpenRouterLyriaMusicGenerator

    return OpenRouterLyriaMusicGenerator(
        s.openrouter_api_key.strip(),  # type: ignore[arg-type]
        base_url=s.openrouter_base_url,
        model=(s.openrouter_music_model or "google/lyria-3-pro-preview").strip(),
        http_referer=s.openrouter_http_referer,
        app_title=s.app_name,
        timeout=float(s.openrouter_music_timeout_seconds or 300.0),
    )
