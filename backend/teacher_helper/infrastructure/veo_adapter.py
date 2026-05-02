from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import httpx

from teacher_helper.use_cases.ports import VideoResult

logger = logging.getLogger(__name__)

_GEMINI_BASE = "https://generativelanguage.googleapis.com"

# Ceny per sekunda (USD) używane do szacowania — mogą być aktualizowane w .env przez veo_price_per_second_usd
_MODEL_PRICE_PER_SECOND: dict[str, float] = {
    "veo-3.1-fast": 0.10,
    "veo-3.1-generate-preview": 0.40,
    "veo-3.0-generate-preview": 0.75,
}

# Natywny zakres czasu jednego klipu Veo (sekundy)
_VEO_MIN_DURATION = 4
_VEO_MAX_DURATION = 8


def estimate_cost_usd(model: str, duration_seconds: int, price_override: float | None = None) -> float:
    """Szacuj koszt generacji w USD."""
    price = price_override if price_override is not None else _MODEL_PRICE_PER_SECOND.get(model, 0.40)
    return price * max(_VEO_MIN_DURATION, min(duration_seconds, _VEO_MAX_DURATION))


class VeoVideoGenerator:
    """Adapter Veo 3.1 (Google Gemini API) implementujący VideoGeneratorPort.

    Używa REST API (predictLongRunning) z async polling — bez SDK google-genai,
    wyłącznie httpx zgodnie z resztą projektu.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "veo-3.1-generate-preview",
        resolution: str = "1080p",
        timeout: float = 300.0,
        poll_interval: float = 10.0,
        price_per_second_usd: float | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._resolution = resolution
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._price_override = price_per_second_usd

    @property
    def price_per_second_usd(self) -> float:
        return self._price_override if self._price_override is not None else _MODEL_PRICE_PER_SECOND.get(self._model, 0.40)

    # ------------------------------------------------------------------
    # VideoGeneratorPort.generate
    # ------------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        duration_seconds: int = 8,
        style: str | None = None,
    ) -> VideoResult:
        duration_seconds = max(_VEO_MIN_DURATION, min(duration_seconds, _VEO_MAX_DURATION))
        full_prompt = f"{prompt}. Visual style: {style}" if style else prompt

        try:
            op_name = await self._start_generation(full_prompt, duration_seconds)
            op_result = await self._poll_until_done(op_name)
            video_bytes = await self._download_video(op_result)
            return VideoResult(
                video_data=video_bytes,
                mime_type="video/mp4",
                prompt_used=full_prompt,
                model=self._model,
                status="completed",
                message=(
                    f"Wygenerowano {duration_seconds} s wideo ({self._resolution}) "
                    f"modelem {self._model}."
                ),
            )
        except asyncio.TimeoutError:
            logger.error("Veo generation timed out after %.0f s", self._timeout)
            return VideoResult(
                video_data=None,
                mime_type="video/mp4",
                prompt_used=full_prompt,
                model=self._model,
                status="failed",
                message=(
                    f"Przekroczono limit czasu oczekiwania ({self._timeout:.0f} s) na odpowiedź Veo. "
                    "Spróbuj ponownie lub skróć czas trwania."
                ),
            )
        except Exception as exc:
            logger.error("Veo generation failed: %s", exc)
            return VideoResult(
                video_data=None,
                mime_type="video/mp4",
                prompt_used=full_prompt,
                model=self._model,
                status="failed",
                message=f"Błąd generowania wideo (Veo): {exc!s}"[:500],
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _start_generation(self, prompt: str, duration_seconds: int) -> str:
        """Wysyła żądanie startowe; zwraca nazwę operacji (do pollingu)."""
        url = f"{_GEMINI_BASE}/v1beta/models/{self._model}:predictLongRunning"
        headers = {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "instances": [{"prompt": prompt}],
            "parameters": {
                "sampleCount": 1,
                "durationSeconds": duration_seconds,
                "aspectRatio": "16:9",
                "resolution": self._resolution,
            },
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            _raise_for_veo_status(resp)
            data: dict[str, Any] = resp.json()

        op_name = data.get("name") or ""
        if not op_name:
            raise RuntimeError(f"Brak 'name' w odpowiedzi startowej Veo: {data!r}")
        logger.debug("Veo operation started: %s", op_name)
        return op_name

    async def _poll_until_done(self, operation_name: str) -> dict[str, Any]:
        """Polluje status operacji aż do zakończenia lub timeoutu."""
        # Jeśli operation_name zaczyna się od "operations/", dodaj prefiks v1beta
        if operation_name.startswith("operations/"):
            url = f"{_GEMINI_BASE}/v1beta/{operation_name}"
        else:
            url = f"{_GEMINI_BASE}/v1beta/{operation_name}"
        headers = {"x-goog-api-key": self._api_key}

        loop = asyncio.get_event_loop()
        deadline = loop.time() + self._timeout

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                if loop.time() >= deadline:
                    raise asyncio.TimeoutError()

                resp = await client.get(url, headers=headers)
                _raise_for_veo_status(resp)
                data: dict[str, Any] = resp.json()

                if data.get("done"):
                    if "error" in data:
                        err = data["error"]
                        msg = err.get("message") if isinstance(err, dict) else str(err)
                        raise RuntimeError(f"Veo zwróciło błąd operacji: {msg}")
                    return data

                await asyncio.sleep(self._poll_interval)

    async def _download_video(self, operation_data: dict[str, Any]) -> bytes:
        """Pobiera bajty wideo z ukończonej operacji Veo."""
        response = operation_data.get("response", {})

        # Struktura Gemini API: response.generateVideoResponse.generatedSamples[].video
        samples = (
            response
            .get("generateVideoResponse", {})
            .get("generatedSamples", [])
        )
        if not samples:
            raise ValueError(f"Brak generatedSamples w odpowiedzi Veo: {response!r}")

        video_info: dict[str, Any] = samples[0].get("video", {})

        # Najpierw spróbuj inline bytes (base64)
        for key in ("videoBytes", "bytesBase64Encoded", "data"):
            inline = video_info.get(key)
            if inline and isinstance(inline, str):
                logger.debug("Veo: inline video bytes via '%s'", key)
                return base64.b64decode(inline)

        # Pobierz z URI
        uri = video_info.get("uri") or video_info.get("videoUri") or ""
        if not uri:
            raise ValueError(f"Brak URI ani inline bytes w odpowiedzi Veo: {video_info!r}")

        logger.debug("Veo: downloading video from URI %s", uri[:80])
        headers = {"x-goog-api-key": self._api_key}
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=300.0)) as client:
            resp = await client.get(uri, headers=headers)
            _raise_for_veo_status(resp)
            return resp.content


def _raise_for_veo_status(resp: httpx.Response) -> None:
    """Rzuca wyjątek z czytelnym komunikatem przy błędzie HTTP."""
    if resp.is_error:
        try:
            body = resp.json()
            detail = body.get("error", {}).get("message") or str(body)[:300]
        except Exception:
            detail = resp.text[:300]
        raise RuntimeError(f"Veo API HTTP {resp.status_code}: {detail}")
