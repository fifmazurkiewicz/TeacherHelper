"""Import audio KIE Suno po taskId (użytkownik zalogowany).

Nie mylić z ``POST /v1/webhooks/kie/music`` — tam callback z serwerów KIE (bez JWT).
"""

from __future__ import annotations

import asyncio
import logging
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from teacher_helper.adapters.http.deps import CurrentUser, DbSession
from teacher_helper.adapters.http.rate_limit import check_rate_limit
from teacher_helper.adapters.http.schemas import FileResponse, KieMusicImportByTaskRequest
from teacher_helper.config import get_settings
from teacher_helper.infrastructure.db.file_ops import index_file_content
from teacher_helper.infrastructure.db.models import FileAssetORM, FileCategory, FileStatus, ProjectORM
from teacher_helper.infrastructure.factories import build_music_generator
from teacher_helper.infrastructure.music_kie import (
    KIE_STATUSES_WITH_POSSIBLE_AUDIO,
    KIE_TERMINAL_FAIL_STATUSES,
    download_audio_url,
    parse_task_record,
)
from teacher_helper.infrastructure.storage.local import LocalStorage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/music/kie", tags=["music-kie"])
_storage = LocalStorage()


@router.post("/import-by-task", response_model=FileResponse)
async def import_kie_music_by_task(
    session: DbSession,
    user: CurrentUser,
    body: KieMusicImportByTaskRequest,
) -> FileAssetORM:
    """Odpytuje ``record-info`` i zapisuje pierwszy dostępny MP3 w bibliotece."""
    check_rate_limit(user)
    task_id = body.task_id.strip()
    if not task_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Pusty task_id")

    pid = body.project_id
    if pid is not None:
        proj = await session.get(ProjectORM, pid)
        if not proj or proj.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Projekt nie znaleziony")

    gen = build_music_generator()
    if gen is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="KIE nie jest skonfigurowane (ustaw KIE_API_KEY).",
        )

    fetch = getattr(gen, "fetch_task_record", None)
    if not callable(fetch):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Adapter KIE bez fetch_task_record")

    s = get_settings()
    timeout = float(s.kie_music_poll_timeout_seconds or 0)
    if timeout <= 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Ustaw KIE_MUSIC_POLL_TIMEOUT_SECONDS > 0, aby import mógł czekać na audio.",
        )

    deadline = time.monotonic() + timeout
    interval = max(0.35, float(s.kie_music_poll_interval_seconds))
    last_st: str | None = None
    mp3_bytes: bytes | None = None
    audio_url: str | None = None

    while time.monotonic() < deadline:
        rec = await fetch(task_id)
        st, urls, perr = parse_task_record(rec)
        last_st = st
        if urls and st in KIE_STATUSES_WITH_POSSIBLE_AUDIO:
            audio_url = urls[0]
            try:
                mp3_bytes = await download_audio_url(audio_url)
            except Exception as exc:
                logger.warning("KIE import: download failed: %s", exc)
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY,
                    detail=f"Nie udało się pobrać pliku audio: {exc!s:.400}",
                ) from exc
            break
        if st in KIE_TERMINAL_FAIL_STATUSES:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                detail=perr or st or "Zadanie KIE zakończone błędem",
            )
        await asyncio.sleep(interval)

    if not mp3_bytes:
        raise HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Brak gotowego audio w czasie {int(timeout)} s (ostatni status: {last_st!r}).",
        )

    stem = f"kie_{task_id[:24]}".replace("/", "_")
    name = f"{stem}_{uuid4().hex[:8]}.mp3"
    extra: dict = {
        "module": "music",
        "kie_task_id": task_id,
        "kie_audio_url": audio_url,
        "import_source": "materials_import_by_task",
    }
    key = await _storage.put(mp3_bytes, prefix=f"u/{user.id}")
    row = FileAssetORM(
        id=uuid4(),
        user_id=user.id,
        project_id=pid,
        topic_id=None,
        name=name,
        category=FileCategory.music,
        mime_type="audio/mpeg",
        storage_key=key,
        version=1,
        size_bytes=len(mp3_bytes),
        status=FileStatus.draft,
        extra=extra,
    )
    session.add(row)
    await session.flush()
    idx = f"KIE import task={task_id}\n{audio_url or ''}".strip()
    await index_file_content(session, row, idx.encode("utf-8"), name)
    await session.commit()
    await session.refresh(row)
    return row
