"""Adapter generowania obrazów przez OpenRouter (chat/completions + modalities image)."""
from __future__ import annotations

import base64
import binascii
import logging
from typing import Any

import httpx

from teacher_helper.use_cases.ports import ImageResult

logger = logging.getLogger(__name__)

SIZE_TO_ASPECT: dict[str, str] = {
    "1024x1024": "1:1",
    "1792x1024": "16:9",
    "1024x1792": "9:16",
    "1248x832": "3:2",
    "832x1248": "2:3",
    "1184x864": "4:3",
    "864x1184": "3:4",
}


def _modalities_for_model(model_id: str) -> list[str]:
    """FLUX / część modeli wymaga wyłącznie ``[\"image\"]``; Gemini zwykle ``[\"image\",\"text\"]``."""
    m = model_id.lower()
    if "gemini" in m:
        return ["image", "text"]
    if "flux" in m or "riverflow" in m or "sourceful" in m:
        return ["image"]
    return ["image", "text"]


def _first_image_url(images: list[Any]) -> str | None:
    for item in images:
        if isinstance(item, str) and item.strip():
            return item.strip()
        if isinstance(item, dict):
            iu = item.get("image_url") or item.get("imageUrl")
            if isinstance(iu, dict) and isinstance(iu.get("url"), str):
                return iu["url"].strip()
            if isinstance(iu, str):
                return iu.strip()
    return None


def _first_image_url_from_message_content(content: Any) -> str | None:
    """Obraz w ``message.content`` jako lista części (OpenRouter / Gemini multimodal)."""
    if not isinstance(content, list):
        return None
    for part in content:
        if not isinstance(part, dict):
            continue
        if part.get("type") in ("image_url", "image"):
            iu = part.get("image_url")
            if isinstance(iu, dict) and isinstance(iu.get("url"), str):
                u = iu["url"].strip()
                if u:
                    return u
            if isinstance(iu, str) and iu.strip():
                return iu.strip()
        url = part.get("url")
        if isinstance(url, str) and url.strip().startswith(("http://", "https://", "data:")):
            return url.strip()
    return None


class OpenRouterImageGenerator:
    """Generowanie obrazów: POST ``/chat/completions`` z ``modalities`` (dokumentacja OpenRouter)."""

    def __init__(
        self,
        api_key: str,
        model: str = "google/gemini-3.1-flash-image-preview",  # OpenRouter: Nano Banana 2
        *,
        base_url: str = "https://openrouter.ai/api/v1",
        http_referer: str | None = None,
        app_title: str | None = None,
        timeout: float = 120.0,
        image_size: str | None = "1K",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base = base_url.rstrip("/")
        self._referer = http_referer
        self._title = app_title
        self._timeout = timeout
        self._image_size = (image_size or "").strip() or None

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self._referer:
            h["HTTP-Referer"] = self._referer
        if self._title:
            h["X-Title"] = self._title
        return h

    @staticmethod
    def _build_prompt(prompt: str, style: str | None) -> str:
        parts = [prompt]
        if style:
            parts.append(f"Styl / style: {style}")
        parts.append(
            "Wygeneruj obraz wysokiej jakości, odpowiedni do materiałów edukacyjnych dla dzieci i młodzieży, "
            "wiernie według opisu; jeśli opis zawiera tekst do umieszczenia na obrazie, zachowaj ten sam język i pisownię."
        )
        return " ".join(parts)

    @staticmethod
    def _bytes_from_data_url(data_url: str) -> bytes | None:
        if not data_url.startswith("data:"):
            return None
        try:
            _, b64 = data_url.split(",", 1)
        except ValueError:
            return None
        try:
            return base64.standard_b64decode(b64)
        except (ValueError, binascii.Error):
            return None

    async def _bytes_from_image_ref(self, client: httpx.AsyncClient, ref: str) -> bytes:
        raw = self._bytes_from_data_url(ref)
        if raw is not None:
            return raw
        if ref.startswith("http://") or ref.startswith("https://"):
            r = await client.get(ref, timeout=self._timeout)
            r.raise_for_status()
            return r.content
        try:
            return base64.standard_b64decode(ref)
        except (ValueError, binascii.Error) as exc:
            raise RuntimeError(f"OpenRouter Image: niepoprawne dane obrazu (nie data URL, nie http, nie base64)") from exc

    async def generate(
        self,
        prompt: str,
        style: str | None = None,
        size: str = "1024x1024",
    ) -> ImageResult:
        full_prompt = self._build_prompt(prompt, style)
        aspect_ratio = SIZE_TO_ASPECT.get(size, "1:1")
        modalities = _modalities_for_model(self._model)

        image_config: dict[str, Any] = {"aspect_ratio": aspect_ratio}
        if self._image_size and "gemini" in self._model.lower():
            image_config["image_size"] = self._image_size

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": full_prompt}],
            "modalities": modalities,
            "image_config": image_config,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(
                f"{self._base}/chat/completions",
                json=payload,
                headers=self._headers(),
            )

        if r.is_error:
            detail = r.text[:800] if r.text else r.reason_phrase
            logger.error("OpenRouter Image HTTP %s: %s", r.status_code, detail)
            raise RuntimeError(f"OpenRouter Image HTTP {r.status_code}: {detail}")

        data = r.json()
        choices = data.get("choices")
        if not choices:
            raise RuntimeError("OpenRouter Image: brak choices w odpowiedzi")

        msg = choices[0].get("message", {})
        if not isinstance(msg, dict):
            raise RuntimeError("OpenRouter Image: nieprawidłowe «message»")

        images_raw = msg.get("images")
        image_ref: str | None = None
        if isinstance(images_raw, list) and images_raw:
            image_ref = _first_image_url(images_raw)

        if not image_ref:
            content = msg.get("content")
            image_data = self._extract_inline_base64(content)
            if image_data:
                text_parts = ""
                if isinstance(content, str):
                    text_parts = content
                return ImageResult(
                    image_data=image_data,
                    mime_type="image/png",
                    prompt_used=prompt,
                    model=self._model,
                    revised_prompt=text_parts[:500] if text_parts else None,
                )
            image_ref = _first_image_url_from_message_content(content)
            if not image_ref:
                preview = repr(content)[:400] if content is not None else "None"
                raise RuntimeError(
                    "OpenRouter Image: brak obrazów w odpowiedzi (sprawdź OPENROUTER_IMAGE_MODEL i modalities). "
                    f"Fragment treści: {preview}"
                )

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            image_bytes = await self._bytes_from_image_ref(client, image_ref)

        text_parts = msg.get("content", "")
        if not isinstance(text_parts, str):
            text_parts = str(text_parts) if text_parts else ""

        mime = "image/png"
        if image_ref.startswith("data:"):
            semi = image_ref.find(";")
            if semi > 5:
                mime = image_ref[5:semi] or mime

        return ImageResult(
            image_data=image_bytes,
            mime_type=mime,
            prompt_used=prompt,
            model=self._model,
            revised_prompt=text_parts[:500] if text_parts else None,
        )

    @staticmethod
    def _extract_inline_base64(content: Any) -> bytes | None:
        """Fallback — inline_data w ``content`` (lista części)."""
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    inline = part.get("inline_data") or part.get("inlineData") or {}
                    if isinstance(inline, dict) and inline.get("data"):
                        try:
                            return base64.standard_b64decode(inline["data"])
                        except (ValueError, binascii.Error):
                            continue
        return None
