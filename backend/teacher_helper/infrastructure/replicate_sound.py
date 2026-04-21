"""Adapter Replicate — generowanie krótkich efektów dźwiękowych (do 30 s).

Używa modelu ``meta/musicgen`` przez Replicate Predictions API:
  POST /v1/models/{owner}/{name}/predictions  → polling GET /v1/predictions/{id}

Dokumentacja: https://replicate.com/meta/musicgen
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from teacher_helper.use_cases.ports import SoundGeneratorPort, SoundResult

logger = logging.getLogger(__name__)

_REPLICATE_BASE = "https://api.replicate.com/v1"
_TERMINAL_OK = frozenset({"succeeded"})
_TERMINAL_FAIL = frozenset({"failed", "canceled"})
_MAX_AUDIO_BYTES = 50 * 1024 * 1024  # 50 MB


class ReplicateSoundGenerator(SoundGeneratorPort):
    """Generuje efekty dźwiękowe przez Replicate API (domyślnie meta/musicgen)."""

    def __init__(
        self,
        api_key: str,
        model: str = "meta/musicgen",
        *,
        musicgen_model_version: str = "stereo-large",
        output_format: str = "mp3",
        timeout: float = 120.0,
        poll_interval: float = 2.0,
    ) -> None:
        self._api_key = api_key
        owner, name = model.split("/", 1)
        self._predict_url = f"{_REPLICATE_BASE}/models/{owner}/{name}/predictions"
        self._model = model
        self._musicgen_model_version = musicgen_model_version
        self._output_format = output_format
        self._timeout = timeout
        self._poll_interval = poll_interval

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def generate(self, prompt: str, duration_seconds: int = 30) -> SoundResult:
        duration = max(1, min(duration_seconds, 30))
        body = {
            "input": {
                "prompt": prompt,
                "duration": duration,
                "model_version": self._musicgen_model_version,
                "output_format": self._output_format,
                "normalization_strategy": "peak",
            }
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(self._predict_url, json=body, headers=self._headers())
            r.raise_for_status()
            prediction = r.json()

        prediction_id: str = prediction["id"]
        poll_url = f"{_REPLICATE_BASE}/predictions/{prediction_id}"
        logger.debug("Replicate prediction created id=%s model=%s", prediction_id, self._model)

        deadline = time.monotonic() + self._timeout
        poll_headers = {"Authorization": f"Bearer {self._api_key}"}

        while True:
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"Replicate prediction {prediction_id} nie zakończyło się w {self._timeout:.0f} s"
                )

            await asyncio.sleep(self._poll_interval)

            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(poll_url, headers=poll_headers)
                r.raise_for_status()
                prediction = r.json()

            status: str = prediction.get("status", "")
            logger.debug("Replicate prediction %s status=%s", prediction_id, status)

            if status in _TERMINAL_OK:
                break
            if status in _TERMINAL_FAIL:
                err = prediction.get("error") or status
                raise RuntimeError(f"Replicate prediction failed: {err!s:.400}")

        output = prediction.get("output")
        if isinstance(output, list):
            audio_url = output[0] if output else None
        else:
            audio_url = output

        if not audio_url:
            raise RuntimeError("Replicate nie zwrócił URL audio w polu 'output'")

        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            r = await client.get(str(audio_url))
            r.raise_for_status()
            audio_bytes = r.content

        if len(audio_bytes) > _MAX_AUDIO_BYTES:
            raise ValueError("audio_response_too_large")

        mime = "audio/mpeg" if self._output_format == "mp3" else "audio/wav"
        logger.info(
            "Replicate sound OK id=%s bytes=%d prompt=%r",
            prediction_id, len(audio_bytes), prompt[:80],
        )
        return SoundResult(
            audio_data=audio_bytes,
            mime_type=mime,
            prompt_used=prompt,
            model=self._model,
            duration_seconds=duration,
        )
