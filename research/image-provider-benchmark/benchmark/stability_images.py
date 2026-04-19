"""Stability AI — Stable Image v2beta (multipart POST)."""

from __future__ import annotations

from typing import Any, Literal

import httpx

StabilityService = Literal["core", "ultra", "sd3"]

ALLOWED_STABILITY_SERVICES: frozenset[str] = frozenset({"core", "ultra", "sd3"})


def stability_generate_url(base_url: str, service: str) -> str:
    root = (base_url or "").strip().rstrip("/") or "https://api.stability.ai"
    svc = (service or "").strip().lower()
    if svc not in ALLOWED_STABILITY_SERVICES:
        raise ValueError(f"Nieobsługiwana usługa Stability: {service!r}")
    return f"{root}/v2beta/stable-image/generate/{svc}"


async def stability_generate_raw(
    *,
    api_key: str,
    base_url: str,
    service: str,
    form_fields: dict[str, Any],
    timeout: float = 180.0,
) -> tuple[bytes | None, list[dict[str, Any]], str | None]:
    trace: list[dict[str, Any]] = []
    try:
        url = stability_generate_url(base_url, service)
    except ValueError as exc:
        return None, trace, str(exc)

    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Accept": "image/*",
    }
    data = {k: str(v) for k, v in form_fields.items() if v is not None and str(v) != ""}
    trace.append(
        {
            "provider": "stability_image",
            "step": 1,
            "POST": url,
            "form_keys": sorted(data.keys()),
        },
    )
    files = {"none": ("", b"")}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, headers=headers, data=data, files=files)
    except httpx.HTTPError as exc:
        return None, trace, f"Stability HTTP: {exc!s:.400}"

    ct = r.headers.get("content-type", "")
    trace.append(
        {
            "provider": "stability_image",
            "step": 2,
            "http_status": r.status_code,
            "content_type": ct[:120],
            "bytes": len(r.content or b""),
        },
    )
    if r.status_code >= 400:
        err_txt = r.text[:1200] if "application/json" in ct or "text/" in ct else "(binary lub pusty body)"
        return None, trace, f"Stability {r.status_code}: {err_txt}"

    if not r.content:
        return None, trace, "Stability: pusty body odpowiedzi"

    if "image" not in ct.lower() and not r.content.startswith(b"\x89PNG"):
        # czasem API zwraca JSON z błędem przy Accept image/*
        try:
            j = r.json()
            if isinstance(j, dict) and (j.get("errors") or j.get("message")):
                return None, trace, str(j)[:900]
        except ValueError:
            pass

    return r.content, trace, None
