"""Adapter generowania obrazów przez OpenRouter (Gemini Image / GPT Image / Flux)."""
from __future__ import annotations

import base64
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


class OpenRouterImageGenerator:
    """Generowanie obrazów przez endpoint chat/completions z modalities=["image","text"]."""

    def __init__(
        self,
        api_key: str,
        model: str = "google/gemini-3.1-flash-image-preview",
        *,
        base_url: str = "https://openrouter.ai/api/v1",
        http_referer: str | None = None,
        app_title: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base = base_url.rstrip("/")
        self._referer = http_referer
        self._title = app_title
        self._timeout = timeout

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

    async def generate(
        self,
        prompt: str,
        style: str | None = None,
        size: str = "1024x1024",
    ) -> ImageResult:
        full_prompt = self._build_prompt(prompt, style)
        aspect_ratio = SIZE_TO_ASPECT.get(size, "1:1")

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": full_prompt}],
            "modalities": ["image", "text"],
            "image_config": {"aspect_ratio": aspect_ratio},
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
        images: list[str] = msg.get("images", [])

        if not images:
            content = msg.get("content", "")
            image_data = self._extract_inline_base64(content)
            if image_data:
                return ImageResult(
                    image_data=image_data,
                    mime_type="image/png",
                    prompt_used=prompt,
                    model=self._model,
                    revised_prompt=None,
                )
            raise RuntimeError(
                "OpenRouter Image: brak obrazów w odpowiedzi. "
                f"Treść: {str(content)[:300]}"
            )

        image_bytes = self._decode_data_url(images[0])
        text_parts = msg.get("content", "")

        return ImageResult(
            image_data=image_bytes,
            mime_type="image/png",
            prompt_used=prompt,
            model=self._model,
            revised_prompt=text_parts[:500] if text_parts else None,
        )

    @staticmethod
    def _build_prompt(prompt: str, style: str | None) -> str:
        parts = [prompt]
        if style:
            parts.append(f"Style: {style}")
        parts.append("Generate this as a high-quality image suitable for children's education.")
        return ". ".join(parts)

    @staticmethod
    def _decode_data_url(data_url: str) -> bytes:
        if data_url.startswith("data:"):
            _, b64 = data_url.split(",", 1)
            return base64.b64decode(b64)
        return base64.b64decode(data_url)

    @staticmethod
    def _extract_inline_base64(content: Any) -> bytes | None:
        """Fallback — wyciąga base64 z inline_data w content (format multipart)."""
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    inline = part.get("inline_data", {})
                    if inline.get("data"):
                        return base64.b64decode(inline["data"])
        return None
