"""OpenRouter — generowanie obrazu przez /chat/completions (modalities)."""

from __future__ import annotations

import base64
import binascii
import re
from typing import Any

import httpx

_DATA_URL_RE = re.compile(r"^data:(image/[\w+.-]+);base64,(.+)$", re.DOTALL)


def build_openrouter_image_body(
    *,
    prompt: str,
    model: str,
    modalities: list[str] | None = None,
    aspect_ratio: str | None = None,
    image_size: str | None = None,
) -> dict[str, Any]:
    mods = modalities if modalities is not None else ["image", "text"]
    body: dict[str, Any] = {
        "model": (model or "").strip(),
        "messages": [{"role": "user", "content": prompt}],
        "modalities": mods,
    }
    ic: dict[str, Any] = {}
    if aspect_ratio:
        ic["aspect_ratio"] = aspect_ratio
    if image_size:
        ic["image_size"] = image_size
    if ic:
        body["image_config"] = ic
    return body


def _decode_data_url(data_url: str) -> tuple[bytes | None, str | None]:
    m = _DATA_URL_RE.match((data_url or "").strip())
    if not m:
        return None, None
    mime, b64part = m.group(1), m.group(2)
    try:
        raw = base64.standard_b64decode(b64part.strip())
    except (ValueError, binascii.Error):
        return None, mime
    return raw, mime


def _images_from_message(msg: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    imgs = msg.get("images")
    if isinstance(imgs, list):
        for im in imgs:
            if not isinstance(im, dict):
                continue
            iu = im.get("image_url") or im.get("imageUrl")
            if isinstance(iu, dict):
                u = iu.get("url")
                if isinstance(u, str):
                    urls.append(u)
            elif isinstance(iu, str):
                urls.append(iu)
    return urls


async def openrouter_image_raw(
    *,
    api_key: str,
    base_url: str,
    http_referer: str | None,
    body: dict[str, Any],
    timeout: float = 180.0,
) -> tuple[bytes | None, list[dict[str, Any]], str | None]:
    trace: list[dict[str, Any]] = []
    root = (base_url or "").strip().rstrip("/") or "https://openrouter.ai/api/v1"
    url = f"{root}/chat/completions"
    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "X-Title": "image-provider-benchmark",
    }
    if http_referer:
        headers["HTTP-Referer"] = http_referer.strip()

    trace.append({"provider": "openrouter_image", "step": 1, "POST": url, "model": body.get("model")})
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, headers=headers, json=body)
    except httpx.HTTPError as exc:
        return None, trace, f"OpenRouter HTTP: {exc!s:.400}"

    trace.append(
        {
            "provider": "openrouter_image",
            "step": 2,
            "http_status": r.status_code,
        },
    )
    if r.status_code >= 400:
        return None, trace, f"OpenRouter {r.status_code}: {r.text[:900]}"

    try:
        payload = r.json()
    except ValueError:
        return None, trace, "OpenRouter: odpowiedź nie-JSON"

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None, trace, f"OpenRouter: brak choices: {str(payload)[:500]}"

    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        return None, trace, "OpenRouter: brak message"

    data_urls = _images_from_message(msg)
    if not data_urls:
        return None, trace, "OpenRouter: brak «message.images» (sprawdź model i «modalities» w JSON)"

    first_url = data_urls[0]
    raw, _mime_hint = _decode_data_url(first_url)
    if raw:
        trace.append({"provider": "openrouter_image", "step": 3, "bytes": len(raw), "source": "data_url"})
        return raw, trace, None

    if first_url.startswith("http"):
        trace.append({"provider": "openrouter_image", "step": 3, "GET": first_url[:400]})
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                gr = await client.get(first_url)
        except httpx.HTTPError as exc:
            return None, trace, f"Pobranie obrazu: {exc!s:.300}"
        if gr.status_code >= 400:
            return None, trace, f"Pobranie obrazu HTTP {gr.status_code}"
        return gr.content, trace, None

    return None, trace, "OpenRouter: nie udało się zdekodować pierwszego obrazu"
