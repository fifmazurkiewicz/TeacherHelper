"""Adapter ElevenLabs — **text-to-sound** (krótkie SFX / foley, nie piosenka).

POST ``https://api.elevenlabs.io/v1/sound-generation`` — jedna odpowiedź (audio binarnie), bez pollingu.
"""

from __future__ import annotations

import json
import logging
import re

import httpx

from teacher_helper.config import get_settings
from teacher_helper.use_cases.ports import SoundGeneratorPort, SoundResult

logger = logging.getLogger(__name__)

_ELEVENLABS_SOUND_URL = "https://api.elevenlabs.io/v1/sound-generation"
_MAX_AUDIO_BYTES = 50 * 1024 * 1024  # 50 MB
_LOG_TEXT_MAX = 4000

# Cały użytkowy opis w docelowym polu `text` powinien być **po angielsku**; jeśli wejście
# ma polskie (lub inne) znaki, przed wysyłką używamy OpenRouter (patrz `elevenlabs_sfx_translate_*`).

_POLISH_DIA = re.compile(r"[\u0105\u0107\u0119\u0142\u0144\u00f3\u015b\u017a\u017c\u0104\u0106\u0118\u0141\u0143\u00d3\u015a\u0179\u017b]")
_CYRILLIC = re.compile(r"[\u0400-\u04FF]")

_SFX_USER_PREFIX = (
    "Non-musical sound effect, foley, ambient or cinematic hit only. "
    "Not a song: no verse/chorus structure, no sung lead vocal, no full track. "
    "One coherent effect. The scene line below is in English. "
)

_TRANSLATE_SYS = (
    "You rewrite a short line into concise English for a text-to-sound effect API. "
    "Foley, ambience, nature, impacts — not music, no song structure. "
    "Output a single line or at most two short lines of English (sound design terms). "
    "No quotes, no labels like 'Output:', English only."
)


def _likely_needs_english_sfx_line(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _POLISH_DIA.search(t) or _CYRILLIC.search(t):
        return True
    return False


def _message_text_from_completion(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text" and "text" in p:
                parts.append(str(p["text"]))
            elif isinstance(p, str):
                parts.append(p)
        return "".join(parts).strip()
    return str(content).strip()


async def _translate_sfx_line_to_english(raw: str) -> str:
    s = get_settings()
    key = (s.openrouter_api_key or "").strip()
    if not key or not s.elevenlabs_sfx_translate_to_english:
        return raw
    model = (s.elevenlabs_sfx_translate_model or "").strip() or (s.openrouter_module_model or "").strip()
    if not model:
        return raw
    base = s.openrouter_base_url.rstrip("/")
    url = f"{base}/chat/completions"
    headers: dict[str, str] = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if (s.openrouter_http_referer or "").strip():
        headers["HTTP-Referer"] = s.openrouter_http_referer.strip()
    payload: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": _TRANSLATE_SYS},
            {"role": "user", "content": (raw or "").strip()[:5000]},
        ],
        "max_tokens": int(s.elevenlabs_sfx_translate_max_tokens),
        "temperature": 0.15,
    }
    tmo = float(s.elevenlabs_sfx_translate_timeout_seconds)
    async with httpx.AsyncClient(timeout=httpx.Timeout(tmo, connect=15.0)) as client:
        r = await client.post(url, json=payload, headers=headers)
    if r.is_error:
        raise RuntimeError(r.text[:600] or r.reason_phrase)
    data = r.json()
    choices = data.get("choices")
    if not choices:
        raise RuntimeError("OpenRouter: brak choices w odpowiedzi tłumaczenia SFX")
    out = _message_text_from_completion((choices[0].get("message") or {}).get("content"))
    if not (out or "").strip():
        return raw
    return out[:4000].strip()


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
        s = get_settings()
        line_for_model = body_prompt
        if body_prompt and _likely_needs_english_sfx_line(body_prompt) and s.elevenlabs_sfx_translate_to_english:
            if (s.openrouter_api_key or "").strip():
                try:
                    line_for_model = await _translate_sfx_line_to_english(body_prompt)
                    if line_for_model and line_for_model != body_prompt:
                        logger.info(
                            "ElevenLabs SFX: opis ujednolicono do EN przed API | in=%r | out=%r",
                            body_prompt[:400],
                            line_for_model[:500],
                        )
                except Exception as exc:
                    logger.warning(
                        "ElevenLabs SFX: tłumaczenie na EN nieudane, wysyłam oryginał: %s",
                        str(exc)[:500],
                    )
                    line_for_model = body_prompt
            else:
                logger.info(
                    "ElevenLabs SFX: w opisie wykryto znaki spoza typowego angielskiego, "
                    "a OPENROUTER_API_KEY brak — wysyłam surowy opis. Ustaw OpenRouter albo opis w EN."
                )
        text = f"{_SFX_USER_PREFIX}\n{line_for_model}".strip()

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
