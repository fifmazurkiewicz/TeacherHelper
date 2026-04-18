from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

from teacher_helper.use_cases.ports import ImageResult

logger = logging.getLogger(__name__)

VALID_SIZES_DALLE3 = {"1024x1024", "1792x1024", "1024x1792"}


class DallEImageGenerator:
    """Adapter generowania obrazów przez OpenAI DALL-E 3 API."""

    def __init__(
        self,
        api_key: str,
        model: str = "dall-e-3",
        *,
        timeout: float = 120.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    async def generate(
        self,
        prompt: str,
        style: str | None = None,
        size: str = "1024x1024",
    ) -> ImageResult:
        dalle_style = self._map_style(style)
        if size not in VALID_SIZES_DALLE3:
            size = "1024x1024"

        payload: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "response_format": "b64_json",
            "style": dalle_style,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(
                "https://api.openai.com/v1/images/generations",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        if r.is_error:
            detail = r.text[:800] if r.text else r.reason_phrase
            logger.error("DALL-E HTTP %s: %s", r.status_code, detail)
            raise RuntimeError(f"DALL-E HTTP {r.status_code}: {detail}")

        data = r.json()
        img_data = data["data"][0]
        image_bytes = base64.b64decode(img_data["b64_json"])

        return ImageResult(
            image_data=image_bytes,
            mime_type="image/png",
            prompt_used=prompt,
            model=self._model,
            revised_prompt=img_data.get("revised_prompt"),
        )

    @staticmethod
    def _map_style(style: str | None) -> str:
        """Mapuje styl z tool calling na wartość DALL-E API (vivid | natural)."""
        if not style:
            return "vivid"
        s = style.lower()
        if any(k in s for k in ("natural", "realistic", "photo", "realistyczn", "zdjęci")):
            return "natural"
        return "vivid"
