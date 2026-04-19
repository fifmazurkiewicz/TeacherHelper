"""Transkrypcja mowy (STT) przez xAI — Grok Speech-to-Text."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from teacher_helper.adapters.http.deps import CurrentUser
from teacher_helper.adapters.http.rate_limit import check_rate_limit
from teacher_helper.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/voice", tags=["voice"])

MAX_AUDIO_BYTES = 15 * 1024 * 1024


class TranscribeResponse(BaseModel):
    text: str


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    user: CurrentUser,
    file: UploadFile = File(...),
) -> TranscribeResponse:
    """Nagraj audio w przeglądarce, wyślij jako multipart — xAI zwraca tekst (język m.in. polski)."""
    check_rate_limit(user)
    s = get_settings()
    key = (s.xai_api_key or "").strip()
    if not key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Transkrypcja głosu nie jest skonfigurowana. Ustaw XAI_API_KEY w .env (klucz z https://console.x.ai).",
        )
    raw = await file.read()
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Pusty plik audio.")
    if len(raw) > MAX_AUDIO_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Plik audio za duży (maks. 15 MB).")

    filename = (file.filename or "recording.webm").strip() or "recording.webm"
    ctype = file.content_type or "application/octet-stream"
    base = s.xai_base_url.rstrip("/")
    url = f"{base}/stt"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
            # Tylko pole `file` — w dokumentacji xAI plik powinien być ostatnim polem multipart.
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {key}"},
                files={"file": (filename, raw, ctype)},
            )
    except httpx.RequestError as exc:
        logger.warning("xAI STT request error: %s", exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="Nie udało się połączyć z usługą transkrypcji (xAI). Spróbuj ponownie.",
        ) from exc

    if resp.status_code >= 400:
        detail = resp.text[:500] if resp.text else resp.reason_phrase
        logger.warning("xAI STT HTTP %s: %s", resp.status_code, detail)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"Transkrypcja nie powiodła się (xAI: {resp.status_code}).",
        )

    try:
        payload: dict[str, Any] = resp.json()
    except Exception as exc:
        logger.warning("xAI STT invalid JSON: %s", resp.text[:300])
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="Nieprawidłowa odpowiedź usługi transkrypcji.",
        ) from exc

    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nie rozpoznano mowy — spróbuj mówić wyraźniej lub zbliż mikrofon.",
        )
    return TranscribeResponse(text=text)
