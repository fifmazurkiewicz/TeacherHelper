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
    VideoGeneratorPort,
)


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

def _build_openrouter(model: str) -> LlmClientPort:
    from teacher_helper.infrastructure.llm_openrouter import OpenRouterLlmClient

    s = get_settings()
    return OpenRouterLlmClient(
        api_key=s.openrouter_api_key,  # type: ignore[arg-type]
        model=model,
        base_url=s.openrouter_base_url,
        http_referer=s.openrouter_http_referer,
        app_title=s.app_name,
    )


def _build_llm(model_attr: str) -> LlmClientPort:
    from teacher_helper.infrastructure.llm_stub import StubLlmClient

    s = get_settings()
    if s.openrouter_api_key:
        return _build_openrouter(getattr(s, model_attr))
    return StubLlmClient()


def build_llm_client() -> LlmClientPort:
    """LLM do orchestracji (tani, szybki)."""
    return _build_llm("openrouter_model")


def build_module_llm_client() -> LlmClientPort:
    """LLM do modułów (reasoning, lepszy model)."""
    return _build_llm("openrouter_module_model")


# ---------------------------------------------------------------------------
# Generatory mediów
# ---------------------------------------------------------------------------

def build_image_generator() -> ImageGeneratorPort | None:
    """OpenRouter (Gemini Image) → DALL-E → None."""
    s = get_settings()
    if s.openrouter_api_key and s.openrouter_image_model:
        from teacher_helper.infrastructure.image_openrouter import OpenRouterImageGenerator

        return OpenRouterImageGenerator(
            api_key=s.openrouter_api_key,
            model=s.openrouter_image_model,
            base_url=s.openrouter_base_url,
            http_referer=s.openrouter_http_referer,
            app_title=s.app_name,
        )
    if s.dalle_api_key:
        from teacher_helper.infrastructure.image_dalle import DallEImageGenerator

        return DallEImageGenerator(api_key=s.dalle_api_key, model=s.dalle_model)
    return None


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
