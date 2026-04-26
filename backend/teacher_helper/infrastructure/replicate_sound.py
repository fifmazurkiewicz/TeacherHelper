"""Adapter Replicate — dwa modele:

- **Krótkie SFX / foley** (``mode=sfx``): **Stable Audio Open** — próbki, ambience, efekty (nie „piosenka”).
- **Krótki utwór / melodia** (``mode=short_music``): **MusicGen (Meta)** — instrumental / lekcja muzyczna.

Ujednolicone API: ``POST /v1/predictions`` + polling ``GET /v1/predictions/{id}``.

Slugs typu ``meta/musicgen`` w polu ``version`` bywają odrzucane (422) — znane modele mapujemy na 64-znakowe id wersji.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time

import httpx

from teacher_helper.use_cases.ports import SoundGeneratorPort, SoundResult

logger = logging.getLogger(__name__)

# Znane wersje (Latest z kart Replicate — można nadpisać w .env pełnym hex).
_MUSICGEN_DEFAULT_VERSION_ID = (
    "671ac645ce5e552cc63a54a2bbff63fcf798043055d2dac5fc9e36a837eedcfb"
)
_STABLE_AUDIO_SFX_DEFAULT_VERSION_ID = (
    "9aff84a639f96d0f7e6081cdea002d15133d0043727f849c40abdd166b7c75a8"
)

_KNOWN_SLUG_TO_VERSION_HEX: dict[str, str] = {
    "meta/musicgen": _MUSICGEN_DEFAULT_VERSION_ID,
    "stackadoc/stable-audio-open-1.0": _STABLE_AUDIO_SFX_DEFAULT_VERSION_ID,
}

_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")

_REPLICATE_BASE = "https://api.replicate.com/v1"
_TERMINAL_OK = frozenset({"succeeded"})
_TERMINAL_FAIL = frozenset({"failed", "canceled"})
_MAX_AUDIO_BYTES = 50 * 1024 * 1024  # 50 MB

_SFX_USER_PREFIX = (
    "Sound effect / foley / ambient only — short non-musical audio. "
    "Not a song: no verse/chorus structure, no lead vocal as a track. "
    "One coherent SFX. "
)
_SFX_NEGATIVE_STABLE = (
    "singing, vocals, lyrics, full song, pop song, choir, verse, chorus, "
    "melodic song structure, podcast, speech"
)
_SHORT_MUSIC_PREFIX = (
    "Short educational music clip (one segment). "
    "Can include simple singing or melody; keep a single clear idea, classroom-friendly, no long suite. "
    "Match the following theme and any lyrics. "
)


def _predict_version_id(model: str) -> str:
    m = (model or "").strip()
    if not m:
        return m
    if _HEX64.match(m):
        return m
    key = m.lower()
    if key in _KNOWN_SLUG_TO_VERSION_HEX:
        return _KNOWN_SLUG_TO_VERSION_HEX[key]
    return m


def _validate_model_string(m: str) -> None:
    if not (m or "").strip():
        raise ValueError("model: pusty")
    m = m.strip()
    if "/" not in m and not _HEX64.match(m):
        raise ValueError("model: użyj 'owner/nazwa' albo 64-znakowego version id")


class ReplicateSoundGenerator(SoundGeneratorPort):
    """SFX przez Stable Audio Open; krótki utwór przez MusicGen."""

    def __init__(
        self,
        api_key: str,
        *,
        sfx_model: str = "stackadoc/stable-audio-open-1.0",
        music_model: str = "meta/musicgen",
        musicgen_model_version: str = "stereo-large",
        output_format: str = "mp3",
        timeout: float = 120.0,
        poll_interval: float = 2.0,
        max_duration_seconds: int = 30,
    ) -> None:
        self._api_key = api_key
        _validate_model_string(sfx_model)
        _validate_model_string(music_model)
        self._sfx_model = sfx_model.strip()
        self._music_model = music_model.strip()
        self._predict_version_sfx = _predict_version_id(self._sfx_model)
        self._predict_version_music = _predict_version_id(self._music_model)
        self._musicgen_model_version = musicgen_model_version
        self._output_format = output_format
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._max_duration_seconds = max(1, min(int(max_duration_seconds), 30))
        self._predictions_url = f"{_REPLICATE_BASE}/predictions"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def _post_and_poll(self, body: dict, *, log_label: str) -> tuple[str, dict]:
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
        logger.debug("Replicate prediction id=%s (%s)", prediction_id, log_label)

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
            logger.debug("Replicate %s status=%s", prediction_id, status)
            if status in _TERMINAL_OK:
                break
            if status in _TERMINAL_FAIL:
                err = prediction.get("error") or status
                raise RuntimeError(f"Replicate prediction failed: {err!s:.400}")

        return prediction_id, prediction

    async def _download_output(self, prediction: dict) -> bytes:
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
            return r.content

    async def generate(
        self, prompt: str, duration_seconds: int = 10, *, mode: str = "sfx",
    ) -> SoundResult:
        cap = self._max_duration_seconds
        duration = max(1, min(int(duration_seconds), cap))
        body_prompt = (prompt or "").strip()
        mlow = (mode or "sfx").lower()
        is_music = mlow in ("short_music", "short-track", "music_short")

        if is_music:
            text = f"{_SHORT_MUSIC_PREFIX}\n\n{body_prompt}"
            body: dict = {
                "version": self._predict_version_music,
                "input": {
                    "prompt": text,
                    "duration": int(duration),
                    "model_version": self._musicgen_model_version,
                    "output_format": self._output_format,
                },
            }
            pred_id, pred = await self._post_and_poll(body, log_label="musicgen")
            audio_bytes = await self._download_output(pred)
            if len(audio_bytes) > _MAX_AUDIO_BYTES:
                raise ValueError("audio_response_too_large")
            mime = "audio/mpeg" if self._output_format == "mp3" else "audio/wav"
            result_model = self._music_model
        else:
            # Stable Audio: SFX, ambience — nie „piosenka”
            text = f"{_SFX_USER_PREFIX}\n{body_prompt}"
            body = {
                "version": self._predict_version_sfx,
                "input": {
                    "prompt": text,
                    "negative_prompt": _SFX_NEGATIVE_STABLE,
                    "seconds_total": int(duration),
                },
            }
            pred_id, pred = await self._post_and_poll(body, log_label="stable_sfx")
            audio_bytes = await self._download_output(pred)
            if len(audio_bytes) > _MAX_AUDIO_BYTES:
                raise ValueError("audio_response_too_large")
            u = str(pred.get("output") or "")
            if ".mp3" in u.lower():
                mime = "audio/mpeg"
            else:
                mime = "audio/wav"
            result_model = self._sfx_model

        logger.info(
            "Replicate sound OK id=%s bytes=%d model=%s prompt=%r",
            pred_id, len(audio_bytes), result_model, prompt[:80],
        )
        return SoundResult(
            audio_data=audio_bytes,
            mime_type=mime,
            prompt_used=prompt,
            model=result_model,
            duration_seconds=duration,
        )
