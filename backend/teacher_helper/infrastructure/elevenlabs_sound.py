"""Adapter ElevenLabs — **text-to-sound** (krótkie SFX / foley, nie piosenka).

POST ``https://api.elevenlabs.io/v1/sound-generation`` — jedna odpowiedź (audio binarnie), bez pollingu.
"""

from __future__ import annotations

import json
import logging

import httpx

from teacher_helper.use_cases.ports import SoundGeneratorPort, SoundResult

logger = logging.getLogger(__name__)

_ELEVENLABS_SOUND_URL = "https://api.elevenlabs.io/v1/sound-generation"
_MAX_AUDIO_BYTES = 50 * 1024 * 1024  # 50 MB
_LOG_TEXT_MAX = 4000

# Angielski prefix — model dobrze rozumie EN; w promptach mamy i treść użytkownika.
_SFX_USER_PREFIX = (
    "Non-musical sound effect, foley, ambient or cinematic hit only. "
    "Not a song: no verse/chorus structure, no sung lead vocal, no full track. "
    "One coherent effect. "
)


class ElevenLabsSoundGenerator(SoundGeneratorPort):
    """SFX / odgłosy — ElevenLabs Text to Sound (eleven_text_to_sound_v2)."""

    def __init__(
        self,
        api_key: str,
        *,
        model_id: str = "eleven_text_to_sound_v2",
        output_format: str = "mp3_44100_128",
        timeout: float = 90.0,
        max_duration_seconds: int = 30,
        prompt_influence: float = 0.3,
    ) -> None:
        if not (api_key or "").strip():
            raise ValueError("ElevenLabs: pusty api_key")
        self._api_key = api_key.strip()
        self._model_id = (model_id or "").strip() or "eleven_text_to_sound_v2"
        self._output_format = (output_format or "mp3_44100_128").strip()
        self._timeout = float(timeout)
        self._max_duration_seconds = max(1, min(int(max_duration_seconds), 30))
        self._prompt_influence = max(0.0, min(1.0, float(prompt_influence)))

    @staticmethod
    def _mime_for_output_format(fmt: str) -> str:
        f = (fmt or "").lower()
        if f.startswith("mp3_") or f.startswith("mp3-"):
            return "audio/mpeg"
        if f.startswith("opus_"):
            return "audio/opus"
        if f.startswith("pcm_") or f.startswith("ulaw_") or f.startswith("alaw_"):
            return "audio/wav"
        return "application/octet-stream"

    async def generate(
        self, prompt: str, duration_seconds: int = 10, *, mode: str = "sfx",
    ) -> SoundResult:
        mlow = (mode or "sfx").lower()
        if mlow in ("short_music", "short-track", "music_short"):
            raise ValueError(
                "Krótki utwór / piosenka nie jest generowany przez SFX — użyj generate_music (KIE + Lyria)."
            )
        if mlow and mlow != "sfx":
            raise ValueError(f"Nieobsługiwany tryb dźwięku: {mode!r} (oczekiwano 'sfx').")

        cap = self._max_duration_seconds
        duration = max(1, min(int(duration_seconds), cap))
        body_prompt = (prompt or "").strip()
        text = f"{_SFX_USER_PREFIX}\n{body_prompt}".strip()

        body: dict = {
            "text": text,
            "model_id": self._model_id,
            "duration_seconds": float(duration),
            "prompt_influence": self._prompt_influence,
            "loop": False,
        }
        params = {"output_format": self._output_format}
        headers = {
            "xi-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/octet-stream, application/json, */*",
        }

        log_body = dict(body)
        _full_t = log_body.get("text") or ""
        if len(_full_t) > _LOG_TEXT_MAX:
            log_body["text"] = (
                _full_t[:_LOG_TEXT_MAX] + f"... [ucięte, łącznie {len(_full_t)} znaków]"
            )
        logger.info(
            "ElevenLabs → POST %s | query=%s | json=%s | headers=Content-Type, Accept, xi-api-key=<ustawiony>",
            _ELEVENLABS_SOUND_URL,
            json.dumps(params, ensure_ascii=False),
            json.dumps(log_body, ensure_ascii=False),
        )

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout, connect=30.0),
            ) as client:
                r = await client.post(
                    _ELEVENLABS_SOUND_URL,
                    params=params,
                    json=body,
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            raise TimeoutError(
                f"ElevenLabs nie odpowiedział w {self._timeout:.0f} s: {exc!s:.200}"
            ) from exc

        if r.status_code >= 400:
            err_detail = r.text
            try:
                err_detail = str(r.json())
            except Exception:
                pass
            logger.warning(
                "ElevenLabs ← HTTP %s | response=%s",
                r.status_code,
                err_detail[:2000] + ("..." if len(err_detail) > 2000 else ""),
            )
            raise RuntimeError(
                f"ElevenLabs {r.status_code} dla {_ELEVENLABS_SOUND_URL!s}: {err_detail!r}"
            )

        content_type = (r.headers.get("content-type") or "").lower()
        logger.info(
            "ElevenLabs ← HTTP %s | Content-Type=%s | body_bytes=%d",
            r.status_code,
            r.headers.get("content-type"),
            len(r.content or b""),
        )
        if "application/json" in content_type:
            j = r.json()
            logger.warning(
                "ElevenLabs ← HTTP 200 ale Content-Type to JSON (oczekiwano audio): %s",
                str(j)[:2000],
            )
            raise RuntimeError(
                f"ElevenLabs zwrócił JSON zamiast audio: {j!r:.800}"
            )

        audio_bytes = r.content
        if not audio_bytes:
            raise RuntimeError("ElevenLabs: pusty plik audio")
        if len(audio_bytes) > _MAX_AUDIO_BYTES:
            raise ValueError("audio_response_too_large")

        mime = self._mime_for_output_format(self._output_format)
        if "audio" in content_type and "/" in content_type:
            mime = content_type.split(";", 1)[0].strip() or mime

        logger.info(
            "ElevenLabs sound OK bytes=%d model=%s prompt=%r",
            len(audio_bytes), self._model_id, prompt[:80],
        )
        return SoundResult(
            audio_data=audio_bytes,
            mime_type=mime,
            prompt_used=prompt,
            model=self._model_id,
            duration_seconds=duration,
        )
