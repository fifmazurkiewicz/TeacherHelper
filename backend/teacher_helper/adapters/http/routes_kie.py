"""Webhook KIE Suno (callback po generacji muzyki).

Skonfiguruj ``KIE_MUSIC_CALLBACK_URL`` na publiczny adres, np.:
``https://<twój-ngrok>.ngrok-free.app/v1/webhooks/kie/music``
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from teacher_helper.config import get_settings
from teacher_helper.infrastructure.db.models import FileAssetORM, FileCategory, FileStatus
from teacher_helper.infrastructure.db.session import async_session_factory
from teacher_helper.infrastructure.kie_webhook import verify_kie_webhook_signature
from teacher_helper.infrastructure.music_kie import download_audio_url
from teacher_helper.infrastructure.storage.factory import get_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/webhooks/kie", tags=["webhooks-kie"])
_storage = get_storage()


def _extract_task_and_tracks(body: dict[str, Any]) -> tuple[str | None, str | None, list[dict[str, Any]]]:
    data = body.get("data")
    if not isinstance(data, dict):
        data = {}
    task_id = data.get("task_id") or body.get("taskId")
    if task_id is not None:
        task_id = str(task_id).strip() or None
    callback_type = data.get("callbackType")
    if callback_type is not None:
        callback_type = str(callback_type)
    raw_tracks = data.get("data")
    tracks: list[dict[str, Any]] = []
    if isinstance(raw_tracks, list):
        tracks = [t for t in raw_tracks if isinstance(t, dict)]
    return task_id, callback_type, tracks


async def _save_vocal_separation(body: dict[str, Any], task_id: str) -> bool:
    """Zapisuje stem-y callbacka KIE dla pliku, który zlecił separację."""
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    info = data.get("vocal_removal_info") or data.get("vocal_separation_info")
    if not isinstance(info, dict):
        return False
    urls = {"instrumental": info.get("instrumental_url"), "vocal": info.get("vocal_url")}
    if not any(isinstance(url, str) and url.strip() for url in urls.values()):
        return False
    async with async_session_factory() as session:
        row = await session.scalar(
            select(FileAssetORM).where(FileAssetORM.extra["kie_vocal_separation_task_id"].astext == task_id)
        )
        if row is None:
            logger.warning("KIE vocal callback without a matching source file: %s", task_id)
            return True
        extra = dict(row.extra or {})
        if extra.get("kie_vocal_separation_status") == "completed":
            return True
        for label, url in urls.items():
            if not isinstance(url, str) or not url.strip():
                continue
            audio = await download_audio_url(url)
            key = await _storage.put(audio, prefix=f"u/{row.user_id}")
            stem = row.name.rsplit(".", 1)[0]
            session.add(FileAssetORM(
                id=uuid4(), user_id=row.user_id, project_id=row.project_id, topic_id=row.topic_id,
                parent_file_id=row.id, name=f"{stem} — {label}.mp3", category=FileCategory.music,
                mime_type="audio/mpeg", storage_key=key, version=1, size_bytes=len(audio),
                status=FileStatus.draft,
                extra={"module": "music", "kie_vocal_separation_task_id": task_id, "source_file_id": str(row.id), "stem": label},
            ))
        extra["kie_vocal_separation_status"] = "completed"
        row.extra = extra
        await session.commit()
    return True


@router.post("/music")
async def kie_music_callback(request: Request) -> dict[str, Any]:
    """Odbiera POST od KIE (etapy ``text`` / ``first`` / ``complete``)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Oczekiwano JSON") from None
    if not isinstance(body, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ciało musi być obiektem JSON")

    task_id, callback_type, tracks = _extract_task_and_tracks(body)
    s = get_settings()
    secret = (s.kie_webhook_hmac_key or "").strip() or None

    ts = request.headers.get("x-webhook-timestamp") or request.headers.get("X-Webhook-Timestamp")
    sig = request.headers.get("x-webhook-signature") or request.headers.get("X-Webhook-Signature")

    if secret:
        if not task_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Brak task_id w JSON — wymagane do weryfikacji podpisu (data.task_id).",
            )
        if not verify_kie_webhook_signature(task_id, ts, sig, secret):
            logger.warning("KIE webhook: odrzucono — niezgodny podpis HMAC (task_id=%r)", task_id)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowy podpis webhooka")

    if not secret and (ts or sig):
        logger.debug("KIE webhook: nagłówki podpisu obecne, ale KIE_WEBHOOK_HMAC_KEY nie ustawiony — akceptacja bez weryfikacji")

    audio_urls: list[str] = []
    for t in tracks:
        u = t.get("audio_url") or t.get("audioUrl")
        if u:
            audio_urls.append(str(u))

    logger.info(
        "KIE music webhook: code=%s callbackType=%s task_id=%s tracks=%d audio_urls=%d",
        body.get("code"),
        callback_type,
        task_id,
        len(tracks),
        len(audio_urls),
    )

    if task_id:
        try:
            await _save_vocal_separation(body, task_id)
        except Exception:
            logger.exception("KIE vocal callback persistence failed: task=%s", task_id)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="Nie udało się zapisać stemów audio") from None

    return {"code": 200, "msg": "ok"}
