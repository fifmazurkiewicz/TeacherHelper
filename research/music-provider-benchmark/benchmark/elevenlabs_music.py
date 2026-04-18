"""ElevenLabs — compose music (POST /v1/music)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx


def build_elevenlabs_compose_body(
    *,
    title: str,
    style: str,
    lyrics: str,
    instrumental: bool,
    model_id: str,
    duration_minutes: float,
    output_format: str = "mp3_44100_64",
) -> dict[str, Any]:
    """Treść JSON do edycji w UI (``output_format`` idzie jako query param przy POST)."""
    ti = (title or "").strip() or "Untitled"
    st = (style or "").strip() or "pop"
    ly = (lyrics or "").strip()
    parts = [
        f"Educational song. Title: {ti}.",
        f"Musical style and mood: {st}.",
    ]
    if instrumental:
        parts.append("Instrumental only — no vocals, suitable for classroom.")
    else:
        parts.append("Include clear vocals. Lyrics / narrative (may adapt wording for singability):")
        parts.append(ly[:6000])
    prompt = "\n".join(parts)
    # API: typowo 3 s – 10 min; benchmark form ma max 5 min.
    ms = int(round(float(duration_minutes) * 60_000))
    ms = max(30_000, min(ms, 600_000))
    return {
        "model_id": (model_id or "music_v1").strip(),
        "prompt": prompt,
        "music_length_ms": ms,
        "output_format": output_format,
    }


async def elevenlabs_compose_raw(
    api_key: str,
    *,
    base_url: str,
    body: dict[str, Any],
    timeout: float = 300.0,
) -> tuple[bytes | None, list[dict[str, Any]], str | None]:
    """``(mp3_bytes, trace, error)`` — odpowiedź 200 to binarny MP3."""
    trace: list[dict[str, Any]] = []
    root = (base_url or "").strip().rstrip("/") or "https://api.elevenlabs.io"
    out_fmt = str(body.get("output_format") or "mp3_44100_64").strip()
    payload = {k: v for k, v in body.items() if k != "output_format"}
    url = f"{root}/v1/music?output_format={quote(out_fmt, safe='')}"
    trace.append(
        {
            "provider": "elevenlabs_music",
            "step": 1,
            "POST": url.split("?")[0],
            "query": {"output_format": out_fmt},
            "json_body_keys": list(payload.keys()),
            "model_id": payload.get("model_id"),
        },
    )
    headers = {
        "xi-api-key": api_key.strip(),
        "Content-Type": "application/json",
        "Accept": "audio/mpeg,*/*",
    }
    tmo = httpx.Timeout(60.0, read=max(120.0, float(timeout)))
    async with httpx.AsyncClient(timeout=tmo) as client:
        r = await client.post(url, json=payload, headers=headers)
        raw_preview = (r.text or "")[:900] if r.text else ""
        trace.append(
            {
                "provider": "elevenlabs_music",
                "step": 2,
                "http_status": r.status_code,
                "content_type": r.headers.get("content-type"),
            },
        )
        if r.is_error:
            return None, trace, f"ElevenLabs HTTP {r.status_code}: {raw_preview}"
        ct = (r.headers.get("content-type") or "").lower()
        data = r.content
        if not data:
            return None, trace, "ElevenLabs: pusty body odpowiedzi"
        if "json" in ct:
            return None, trace, f"ElevenLabs: nieoczekiwany JSON zamiast audio: {raw_preview}"
        if len(data) > 80 * 1024 * 1024:
            return None, trace, "ElevenLabs: plik audio zbyt duży"
        return data, trace, None
