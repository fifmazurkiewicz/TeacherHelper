"""Adapter Replicate — efekty dźwiękowe / foley oraz krótkie klipy (MusicGen, limit w konfiguracji).

Używa ujednoliconego Replicate API (2025+):
  POST /v1/predictions  z polami ``version`` (np. ``meta/musicgen``) i ``input``  →  polling GET /v1/predictions/{id}

Starszy endpoint ``/v1/models/.../predictions`` bywa zwracany jako 404 — nie używamy go.

Dokumentacja: https://replicate.com/meta/musicgen
"""

from __future__ import annotations

import asyncio
import logging
import re
import time

import httpx

from teacher_helper.use_cases.ports import SoundGeneratorPort, SoundResult

logger = logging.getLogger(__name__)

# Ujednolicone POST /v1/predictions wymaga w polu `version` **64-znakowego** id wersji modelu
# albo slugów typu oficjalnych; slug `meta/musicgen` bywa odrzucany (422) — mapujemy na aktualną
# wersję domyślną z karty Replicate (możesz w .env podać własne 64 znaki w REPLICATE_SOUND_MODEL).
_MUSICGEN_DEFAULT_VERSION_ID = (
    "671ac645ce5e552cc63a54a2bbff63fcf798043055d2dac5fc9e36a837eedcfb"
)
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")

_REPLICATE_BASE = "https://api.replicate.com/v1"
_TERMINAL_OK = frozenset({"succeeded"})
_TERMINAL_FAIL = frozenset({"failed", "canceled"})
_MAX_AUDIO_BYTES = 50 * 1024 * 1024  # 50 MB
_SFX_PROMPT_PREFIX = (
    "Sound effect / foley / ambient only — short non-musical audio. "
    "Not a song, not a melody with structure, no vocals, no full instrumental track. "
    "One coherent SFX matching the description. "
)
_SHORT_MUSIC_PREFIX = (
    "Short educational music clip (one segment). "
    "Can include simple singing or melody; keep a single clear idea, classroom-friendly, no long suite. "
    "Match the following theme and any lyrics. "
)


def _predict_version_id(model: str) -> str:
    """
    Dla `POST /v1/predictions` — pole ``version`` musi wskazywać działającą wersję.
    64 znaki hex = id wersji; inaczej (np. meta/musicgen) podmieniamy na znaną wersję MusicGen.
    Inne `owner/nazwa` przekazujemy bez zmian.
    """
    m = (model or "").strip()
    if not m:
        return m
    if _HEX64.match(m):
        return m
    if m.lower() == "meta/musicgen":
        return _MUSICGEN_DEFAULT_VERSION_ID
    return m


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
        max_duration_seconds: int = 30,
    ) -> None:
        self._api_key = api_key
        m = (model or "").strip()
        if not m:
            raise ValueError("replicate_sound_model: pusty model")
        if "/" not in m and not _HEX64.match(m):
            raise ValueError(
                "replicate_sound_model: użyj 'owner/nazwa' (np. meta/musicgen) albo 64-znakowego version id"
            )
        self._predictions_url = f"{_REPLICATE_BASE}/predictions"
        self._model = m
        self._predict_version = _predict_version_id(m)
        self._musicgen_model_version = musicgen_model_version
        self._output_format = output_format
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._max_duration_seconds = max(1, min(int(max_duration_seconds), 30))

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def generate(
        self, prompt: str, duration_seconds: int = 10, *, mode: str = "sfx",
    ) -> SoundResult:
        cap = self._max_duration_seconds
        duration = max(1, min(int(duration_seconds), cap))
        body_prompt = (prompt or "").strip()
        if (mode or "sfx").lower() in ("short_music", "short-track", "music_short"):
            sfx_prompt = f"{_SHORT_MUSIC_PREFIX}\n\n{body_prompt}"
        else:
            sfx_prompt = f"{_SFX_PROMPT_PREFIX}\n\nOpis / description: {body_prompt}"
        # Minimalne, zgodne ze schematem Cog (replicate.com/meta/musicgen): bez
        # normalization_strategy — domyślna strategia na serwerze (loudness) jest bezpieczna.
        body: dict = {
            "version": self._predict_version,
            "input": {
                "prompt": sfx_prompt,
                "duration": int(duration),
                "model_version": self._musicgen_model_version,
                "output_format": self._output_format,
            },
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(self._predictions_url, json=body, headers=self._headers())
        if r.status_code >= 400:
            try:
                err_body = r.json()
            except Exception:
                err_body = r.text
            raise RuntimeError(
                f"Replicate {r.status_code} dla {self._predictions_url!s}: {err_body!r}"
            )
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
