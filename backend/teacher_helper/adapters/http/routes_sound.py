"""Generowanie krótkich efektów dźwiękowych przez Replicate (Stable Audio Open — SFX).

Endpoint: POST /v1/sound/generate
"""

from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from teacher_helper.adapters.http.deps import CurrentUser, DbSession
from teacher_helper.adapters.http.rate_limit import check_rate_limit
from teacher_helper.adapters.http.schemas import FileResponse, SoundGenerateRequest
from teacher_helper.infrastructure.db.file_ops import index_file_content
from teacher_helper.infrastructure.db.models import FileAssetORM, FileCategory, FileStatus, ProjectORM
from teacher_helper.infrastructure.db.llm_usage import record_langfuse_model_call_sync
from teacher_helper.infrastructure.factories import build_sound_generator
from teacher_helper.infrastructure.storage.local import LocalStorage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/sound", tags=["sound"])
_storage = LocalStorage()


@router.post("/generate", response_model=FileResponse)
async def generate_sound(
    session: DbSession,
    user: CurrentUser,
    body: SoundGenerateRequest,
) -> FileAssetORM:
    """Generuje krótki efekt dźwiękowy (SFX, do 10 s), nie piosenkę — zapis w bibliotece."""
    check_rate_limit(user)

    gen = build_sound_generator()
    if gen is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Replicate nie jest skonfigurowane — ustaw REPLICATE_API_KEY w .env.",
        )

    pid = body.project_id
    if pid is not None:
        proj = await session.get(ProjectORM, pid)
        if not proj or proj.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Projekt nie znaleziony")

    try:
        result = await gen.generate(
            body.prompt, duration_seconds=body.duration_seconds, mode="sfx",
        )
    except TimeoutError as exc:
        logger.warning("Replicate timeout for user=%s: %s", user.id, exc)
        raise HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Generowanie dźwięku przekroczyło limit czasu: {exc!s:.300}",
        ) from exc
    except Exception as exc:
        logger.error("Replicate error for user=%s: %s", user.id, exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"Błąd generowania dźwięku: {exc!s:.400}",
        ) from exc

    await asyncio.to_thread(
        record_langfuse_model_call_sync,
        observation_name="replicate:sound_effect",
        model=result.model,
        provider="replicate",
        input_data={"prompt": body.prompt, "duration_seconds": body.duration_seconds},
        output_text=f"audio bytes={len(result.audio_data)} mime={result.mime_type}",
        user_id=user.id,
        metadata={"call_kind": "sound_effect", "module": "sound"},
        usage=None,
    )

    ext = "mp3" if result.mime_type == "audio/mpeg" else "wav"
    name = f"sfx_{uuid4().hex[:12]}.{ext}"
    extra: dict = {
        "module": "sound",
        "kind": "sfx",
        "prompt": body.prompt,
        "duration_seconds": result.duration_seconds,
        "replicate_model": result.model,
    }

    key = await _storage.put(result.audio_data, prefix=f"u/{user.id}")
    row = FileAssetORM(
        id=uuid4(),
        user_id=user.id,
        project_id=pid,
        topic_id=None,
        name=name,
        category=FileCategory.other,
        mime_type=result.mime_type,
        storage_key=key,
        version=1,
        size_bytes=len(result.audio_data),
        status=FileStatus.draft,
        extra=extra,
    )
    session.add(row)
    await session.flush()
    await index_file_content(
        session, row,
        f"Krótki efekt dźwiękowy (SFX, nie piosenka): {body.prompt}".encode("utf-8"),
        name,
    )
    await session.commit()
    await session.refresh(row)
    return row
