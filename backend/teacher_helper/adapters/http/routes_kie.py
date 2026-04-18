"""Webhook KIE Suno (callback po generacji muzyki).

Skonfiguruj ``KIE_MUSIC_CALLBACK_URL`` na publiczny adres, np.:
``https://<twój-ngrok>.ngrok-free.app/v1/webhooks/kie/music``
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from teacher_helper.config import get_settings
from teacher_helper.infrastructure.kie_webhook import verify_kie_webhook_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/webhooks/kie", tags=["webhooks-kie"])


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

    # Tu można później: dopasowanie task_id → user, zapis pliku MP3 do storage itd.
    return {"code": 200, "msg": "ok"}
