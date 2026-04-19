from __future__ import annotations

from teacher_helper.config import get_settings
from teacher_helper.use_cases.ports import ImageGeneratorPort, VideoGeneratorPort


def build_image_generator() -> ImageGeneratorPort | None:
    """Grafika wyłącznie przez OpenRouter — ten sam kontrakt co ``factories.build_image_generator``."""
    from teacher_helper.infrastructure.factories import build_image_generator as _build

    return _build()


def build_video_generator() -> VideoGeneratorPort | None:
    """Tworzy adapter generowania wideo.

    Aktualnie brak produkcyjnych adapterów — zwraca None (fallback na storyboard JSON).
    """
    return None
