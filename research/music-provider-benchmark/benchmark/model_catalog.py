"""Katalogi modeli dla UI benchmarku: KIE Suno, WaveSpeed MiniMax, OpenRouter Lyria (max 10), OpenRouter wideo (Seedance), ElevenLabs Music."""

from __future__ import annotations

from typing import Any

import httpx

# Gdy brak klucza lub błąd API — minimalny zestaw z dokumentacji OpenRouter (Lyria 3).
_FALLBACK_OPENROUTER_MUSIC: list[dict[str, str]] = [
    {"id": "google/lyria-3-pro-preview", "label": "Lyria 3 Pro Preview — pełny utwór"},
    {"id": "google/lyria-3-pro-preview-20260330", "label": "Lyria 3 Pro Preview (snapshot datowany)"},
]

# Kolejność preferowana przy sortowaniu (reszta alfabetycznie).
_RANK: dict[str, int] = {
    "google/lyria-3-pro-preview": 0,
    "google/lyria-3-pro-preview-20260330": 1,
}

ELEVENLABS_MUSIC_MODELS: list[dict[str, str]] = [
    {"id": "music_v1", "label": "Eleven Music (music_v1)"},
]

# Modele Suno w KIE; V4_5ALL pierwszy — domyślny w TeacherHelper i w selectach UI.
KIE_SUNO_MODELS: list[dict[str, str]] = [
    {"id": "V4_5ALL", "label": "Suno V4_5ALL"},
    {"id": "V5_5", "label": "Suno V5_5"},
    {"id": "V5", "label": "Suno V5"},
    {"id": "V4_5PLUS", "label": "Suno V4_5PLUS"},
    {"id": "V4", "label": "Suno V4"},
]

WAVESPEED_MINIMAX_VARIANTS: list[dict[str, str]] = [
    {"id": "music-2.6", "label": "MiniMax Music 2.6 (WaveSpeed)"},
    {"id": "music-02", "label": "MiniMax Music 02 (WaveSpeed)"},
]

# Wideo przez OpenRouter (Seedance); identyfikatory jak w katalogu OR.
OPENROUTER_VIDEO_MODELS: list[dict[str, str]] = [
    {"id": "bytedance/seedance-1-5-pro", "label": "Seedance 1.5 Pro (wideo z audio)"},
]


async def fetch_openrouter_music_model_ids(*, api_key: str | None, base_url: str) -> list[dict[str, str]]:
    """Zwraca max 10 modeli z OpenRouter, których ``id`` zawiera ``lyria`` (generacja muzyki w katalogu OR)."""
    root = (base_url or "").strip().rstrip("/")
    if not root or not (api_key or "").strip():
        return list(_FALLBACK_OPENROUTER_MUSIC)[:10]

    url = f"{root}/models"
    headers = {"Authorization": f"Bearer {api_key.strip()}", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.get(url, headers=headers)
            if r.is_error:
                return list(_FALLBACK_OPENROUTER_MUSIC)[:10]
            payload: Any = r.json()
    except Exception:
        return list(_FALLBACK_OPENROUTER_MUSIC)[:10]

    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return list(_FALLBACK_OPENROUTER_MUSIC)[:10]

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        mid = str(item.get("id") or "").strip()
        if not mid or "lyria" not in mid.lower():
            continue
        if "clip" in mid.lower():
            continue
        if mid in seen:
            continue
        seen.add(mid)
        name = str(item.get("name") or "").strip() or mid
        out.append({"id": mid, "label": name})

    if not out:
        return list(_FALLBACK_OPENROUTER_MUSIC)[:10]

    out.sort(key=lambda d: (_RANK.get(d["id"], 50), d["id"].lower()))
    return out[:10]
