"""OpenAI Images API — POST /v1/images/generations (np. DALL·E 3)."""

from __future__ import annotations

import base64
import binascii
from typing import Any

import httpx


async def openai_images_generate_raw(
    *,
    api_key: str,
    base_url: str,
    body: dict[str, Any],
    timeout: float = 120.0,
) -> tuple[bytes | None, list[dict[str, Any]], str | None]:
    """Zwraca surowe bajty obrazu (z ``b64_json``) lub błąd."""
    trace: list[dict[str, Any]] = []
    root = (base_url or "").strip().rstrip("/") or "https://api.openai.com"
    url = f"{root}/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }
    trace.append(
        {
            "provider": "openai_images",
            "step": 1,
            "POST": url,
            "json": {k: v for k, v in body.items() if k != "user"},
        },
    )
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, headers=headers, json=body)
    except httpx.HTTPError as exc:
        return None, trace, f"OpenAI HTTP: {exc!s:.400}"

    trace.append(
        {
            "provider": "openai_images",
            "step": 2,
            "http_status": r.status_code,
            "content_type": r.headers.get("content-type", ""),
        },
    )
    if r.status_code >= 400:
        return None, trace, f"OpenAI {r.status_code}: {r.text[:800]}"

    try:
        payload = r.json()
    except ValueError:
        return None, trace, "OpenAI: odpowiedź nie-JSON"

    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return None, trace, f"OpenAI: brak «data» w odpowiedzi: {str(payload)[:500]}"

    first = data[0]
    if not isinstance(first, dict):
        return None, trace, "OpenAI: nieprawidłowy element «data[0]»"

    b64 = first.get("b64_json")
    if isinstance(b64, str) and b64.strip():
        try:
            raw = base64.standard_b64decode(b64.strip())
        except (ValueError, binascii.Error) as exc:
            return None, trace, f"OpenAI: błąd dekodowania b64_json: {exc!s:.200}"
        trace.append({"provider": "openai_images", "step": 3, "bytes": len(raw)})
        return raw, trace, None

    url_img = first.get("url")
    if isinstance(url_img, str) and url_img.startswith("http"):
        trace.append({"provider": "openai_images", "step": 3, "url": url_img[:300]})
        try:
            async with httpx.AsyncClient(timeout=timeout) as dl:
                dr = await dl.get(url_img)
        except httpx.HTTPError as exc:
            return None, trace, f"Pobranie URL obrazu: {exc!s:.300}"
        if dr.status_code >= 400:
            return None, trace, f"Pobranie obrazu HTTP {dr.status_code}"
        return dr.content, trace, None

    return None, trace, "OpenAI: brak «b64_json» ani «url» w pierwszym elemencie data"
