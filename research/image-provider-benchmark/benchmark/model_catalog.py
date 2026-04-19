"""Katalogi modeli / usług do UI: OpenAI Images, Stability Stable Image, OpenRouter (output_modalities=image)."""

from __future__ import annotations

from typing import Any

import httpx

_FALLBACK_OPENROUTER_IMAGE: list[dict[str, str]] = [
    {"id": "black-forest-labs/flux.2-pro", "label": "FLUX.2 Pro (OpenRouter)"},
    {"id": "google/gemini-2.5-flash-image", "label": "Gemini 2.5 Flash Image (OpenRouter)"},
    {"id": "google/gemini-3.1-flash-image-preview", "label": "Gemini 3.1 Flash Image Preview (OpenRouter)"},
]

_RANK: dict[str, int] = {
    "black-forest-labs/flux.2-pro": 0,
    "google/gemini-3.1-flash-image-preview": 1,
    "google/gemini-2.5-flash-image": 2,
}

OPENAI_IMAGE_MODELS: list[dict[str, str]] = [
    {"id": "dall-e-3", "label": "DALL·E 3"},
    {"id": "dall-e-2", "label": "DALL·E 2"},
]

# Ścieżka v2beta: /v2beta/stable-image/generate/{service}
STABILITY_IMAGE_SERVICES: list[dict[str, str]] = [
    {"id": "core", "label": "Stable Image Core"},
    {"id": "ultra", "label": "Stable Image Ultra"},
    {"id": "sd3", "label": "Stable Diffusion 3 (sd3)"},
]


def _has_image_output(mod: dict[str, Any]) -> bool:
    om = mod.get("output_modalities") or mod.get("architecture", {}).get("output_modalities")
    if isinstance(om, list):
        return any(str(x).lower() == "image" for x in om)
    if isinstance(om, str):
        return "image" in om.lower()
    return False


async def fetch_openrouter_image_model_ids(
    *,
    api_key: str | None,
    base_url: str,
    limit: int = 12,
) -> list[dict[str, str]]:
    """Zwraca do ``limit`` modeli z OpenRouter z obsługą wyjścia obrazu (wg pola ``output_modalities``)."""
    root = (base_url or "").strip().rstrip("/")
    if not root:
        return list(_FALLBACK_OPENROUTER_IMAGE)[:limit]
    url = f"{root}/models"
    params = {"output_modalities": "image"}
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url, params=params, headers=headers)
            if r.status_code >= 400:
                return list(_FALLBACK_OPENROUTER_IMAGE)[:limit]
            payload = r.json()
    except (httpx.HTTPError, ValueError):
        return list(_FALLBACK_OPENROUTER_IMAGE)[:limit]

    raw = payload.get("data")
    if not isinstance(raw, list):
        return list(_FALLBACK_OPENROUTER_IMAGE)[:limit]

    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        mid = str(item.get("id") or "").strip()
        if not mid or not _has_image_output(item):
            continue
        name = str(item.get("name") or mid)
        out.append({"id": mid, "label": f"{name} — {mid}"})

    def sort_key(d: dict[str, str]) -> tuple[int, str]:
        i = _RANK.get(d["id"], 999)
        return (i, d["id"])

    out.sort(key=sort_key)
    if not out:
        return list(_FALLBACK_OPENROUTER_IMAGE)[:limit]
    return out[:limit]
