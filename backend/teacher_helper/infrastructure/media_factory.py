from __future__ import annotations

from teacher_helper.config import get_settings
from teacher_helper.use_cases.ports import ImageGeneratorPort, VideoGeneratorPort


def build_image_generator() -> ImageGeneratorPort | None:
    """Tworzy adapter generowania obrazów na podstawie konfiguracji.

    Priorytet: OpenRouter (Gemini Image) → DALL-E → None (fallback na sam prompt).
    """
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
    """Tworzy adapter generowania wideo.

    Aktualnie brak produkcyjnych adapterów — zwraca None (fallback na storyboard JSON).
    """
    return None
