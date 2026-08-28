"""Współdzielone instancje orchestratora czatu (routes + job runner)."""
from __future__ import annotations

import logging

from teacher_helper.infrastructure.db.models import MessageORM
from teacher_helper.infrastructure.factories import (
    build_image_generator,
    build_llm_client,
    build_lyria_music_generator,
    build_module_llm_client,
    build_music_generator,
    build_sound_generator,
    build_summary_llm_client,
    build_video_generator,
)
from teacher_helper.infrastructure.storage.factory import get_storage
from teacher_helper.use_cases.chat_orchestrator import ChatOrchestratorUseCase

logger = logging.getLogger(__name__)

_llm = build_llm_client()
_llm_summary = build_summary_llm_client()
_llm_modules = build_module_llm_client()
_storage = get_storage()
_image_gen = build_image_generator()
_video_gen = build_video_generator()
_music_gen = build_music_generator()
_sound_gen = build_sound_generator()
_lyria_music = build_lyria_music_generator()
orchestrator = ChatOrchestratorUseCase(
    _llm,
    _storage,
    image_gen=_image_gen,
    video_gen=_video_gen,
    music_gen=_music_gen,
    sound_gen=_sound_gen,
    lyria_music=_lyria_music,
    llm_modules=_llm_modules,
)

logger.debug(
    "Chat services initialised: llm=%s, image=%s, video=%s",
    type(_llm).__name__,
    type(_image_gen).__name__ if _image_gen else None,
    type(_video_gen).__name__ if _video_gen else None,
)


def message_pair_for_orchestrator_llm(m: MessageORM) -> tuple[str, str]:
    role = m.role
    content = (m.content or "").strip()
    if role != "assistant":
        return (role, content)
    extra = m.extra
    if not isinstance(extra, dict):
        return (role, content)
    annex: list[str] = []
    mods = extra.get("run_modules")
    if isinstance(mods, list) and mods:
        parts = [str(x).strip() for x in mods if x]
        if parts:
            annex.append("[W tej odpowiedzi wygenerowano moduły: " + ", ".join(parts) + ".]")
    files = extra.get("created_files")
    if isinstance(files, list) and files:
        names: list[str] = []
        for item in files[:35]:
            if isinstance(item, dict) and item.get("name"):
                names.append(str(item["name"]))
            elif isinstance(item, str) and item.strip():
                names.append(item.strip())
        if names:
            annex.append("[Pliki zapisane w bibliotece:\n" + "\n".join(f"  • {n}" for n in names) + "]")
    if annex:
        content = content + "\n\n" + "\n".join(annex)
    return (role, content)
