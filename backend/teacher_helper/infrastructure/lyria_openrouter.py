"""OpenRouter — Google Lyria (muzyka przez ``POST /v1/chat/completions``, SSE + audio).

Logika zgodna z benchmarkiem ``research/music-provider-benchmark`` (stream:true).
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

import httpx

DEFAULT_LYRIA_MODEL = "google/lyria-3-pro-preview"


def build_lyria_openrouter_body(
    *,
    title: str,
    style: str,
    lyrics: str,
    instrumental: bool,
    model: str | None = None,
    variation_suffix: str = "",
) -> dict[str, Any]:
    ti = (title or "").strip() or "Untitled"
    st = (style or "").strip() or "pop"
    ly = (lyrics or "").strip()
    parts = [
        f"Generate a complete song. Title: {ti}.",
        f"Style / mood: {st}.",
    ]
    if instrumental:
        parts.append("Instrumental only — no vocals.")
    else:
        parts.append("Include vocals. Lyrical content (paraphrase if needed):")
        parts.append(ly[:8000])
    text = "\n".join(parts)
    vs = (variation_suffix or "").strip()
    if vs:
        text = f"{text}\n\n{vs}"
    mid = (model or "").strip() or DEFAULT_LYRIA_MODEL
    return {
        "model": mid,
        "messages": [{"role": "user", "content": [{"type": "text", "text": text}]}],
        "modalities": ["text", "audio"],
        "audio": {"format": "wav"},
    }


def _lyria_ensure_audio_request(body: dict[str, Any]) -> dict[str, Any]:
    out = dict(body)
    mid = str(out.get("model") or "").lower()
    if "lyria" not in mid:
        return out
    if not out.get("modalities"):
        out["modalities"] = ["text", "audio"]
    aud = out.get("audio")
    if not isinstance(aud, dict):
        out["audio"] = {"format": "wav"}
    else:
        aud.setdefault("format", "wav")
        out["audio"] = aud
    return out


def _http_headers(api_key: str, referer: str | None, app_title: str) -> dict[str, str]:
    h: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if referer:
        h["HTTP-Referer"] = referer.strip()
    h["X-Title"] = (app_title or "TeacherHelper").strip()[:120]
    return h


async def _lyria_stream_collect_audio(
    client: httpx.AsyncClient,
    url: str,
    base_body: dict[str, Any],
    headers: dict[str, str],
    read_timeout: float,
) -> tuple[list[str], list[str], dict[str, Any] | None, str | None]:
    req = {**base_body, "stream": True}
    req.pop("stream_options", None)
    all_urls: list[str] = []
    all_b64: list[str] = []
    text_buf: list[str] = []
    list_buf: list[Any] = []
    last_msg: dict[str, Any] | None = None
    last_chunk: dict[str, Any] | None = None
    try:
        tmo = httpx.Timeout(60.0, read=max(300.0, float(read_timeout)))
        async with client.stream("POST", url, json=req, headers=headers, timeout=tmo) as resp:
            if resp.status_code >= 400:
                raw = (await resp.aread()).decode(errors="replace")
                return [], [], None, raw[:1600]
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk: Any = json.loads(payload)
                except Exception:
                    continue
                if not isinstance(chunk, dict):
                    continue
                last_chunk = chunk
                _walk_audio_hints(chunk, all_urls, all_b64)
                chs = chunk.get("choices")
                if not isinstance(chs, list) or not chs:
                    continue
                ch0 = chs[0]
                if not isinstance(ch0, dict):
                    continue
                delta = ch0.get("delta")
                if isinstance(delta, dict):
                    _walk_audio_hints(delta, all_urls, all_b64)
                    c = delta.get("content")
                    if isinstance(c, str) and c:
                        text_buf.append(c)
                    elif isinstance(c, list):
                        for part in c:
                            list_buf.append(part)
                            if isinstance(part, dict):
                                _walk_audio_hints(part, all_urls, all_b64)
                msg = ch0.get("message")
                if isinstance(msg, dict) and msg:
                    last_msg = msg
                    _walk_audio_hints(msg, all_urls, all_b64)
    except httpx.ReadTimeout as exc:
        return all_urls, all_b64, last_chunk, f"SSE Lyria: timeout odczytu ({exc!s:.200})"

    all_urls = list(dict.fromkeys(all_urls))
    synthetic: dict[str, Any] | None = None
    if list_buf:
        synthetic = {"choices": [{"message": {"role": "assistant", "content": list_buf}}]}
    elif text_buf:
        synthetic = {"choices": [{"message": {"role": "assistant", "content": "".join(text_buf)}}]}
    elif last_msg is not None:
        synthetic = {"choices": [{"message": dict(last_msg)}]}
    if synthetic is not None:
        eu, eb = _lyria_extra_urls_and_b64(synthetic)
        all_urls.extend(eu)
        all_b64.extend(eb)
        _walk_audio_hints(synthetic, all_urls, all_b64)
    all_urls = list(dict.fromkeys(all_urls))
    return all_urls, all_b64, synthetic or last_chunk, None


def _lyria_extra_urls_and_b64(data: Any) -> tuple[list[str], list[str]]:
    urls: list[str] = []
    b64s: list[str] = []
    if not isinstance(data, dict):
        return urls, b64s
    chs = data.get("choices")
    if not isinstance(chs, list):
        return urls, b64s
    url_in_text = re.compile(
        r"https?://[^\s\"'<>]+\.(?:mp3|wav|m4a|ogg|aac|flac)(?:\?[^\s\"'<>]*)?",
        re.IGNORECASE,
    )
    for ch in chs:
        if not isinstance(ch, dict):
            continue
        msg = ch.get("message")
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                for blob in (part, part.get("input_audio"), part.get("output_audio")):
                    if not isinstance(blob, dict):
                        continue
                    u = blob.get("url") or blob.get("uri") or blob.get("href")
                    if isinstance(u, str) and u.startswith("http"):
                        urls.append(u)
                au = part.get("audio_url")
                if isinstance(au, dict):
                    u2 = au.get("url")
                    if isinstance(u2, str) and u2.startswith("http"):
                        urls.append(u2)
                elif isinstance(au, str) and au.startswith("http"):
                    urls.append(au)
                inline = part.get("inline_data") or part.get("inlineData")
                if isinstance(inline, dict):
                    mime = str(inline.get("mime_type") or inline.get("mimeType") or "").lower()
                    rawd = inline.get("data")
                    if "audio" in mime and isinstance(rawd, str) and len(rawd) > 80:
                        b64s.append(rawd.replace("\n", "").replace(" ", ""))
                for key in ("data", "b64_json", "audio"):
                    raw = part.get(key)
                    if isinstance(raw, str) and len(raw) > 200 and re.match(r"^[A-Za-z0-9+/=\s]+$", raw[:300]):
                        b64s.append(raw.replace("\n", "").replace(" ", ""))
        elif isinstance(content, str):
            for m in url_in_text.finditer(content):
                urls.append(m.group(0))
    return urls, b64s


def _walk_audio_hints(obj: Any, urls: list[str], b64s: list[str]) -> None:
    if isinstance(obj, dict):
        for _k, v in obj.items():
            if isinstance(v, str):
                s = v.strip()
                if s.startswith("http") and any(
                    s.split("?", 1)[0].lower().endswith(ext)
                    for ext in (".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac")
                ):
                    urls.append(s)
                elif len(s) > 200 and re.match(r"^[A-Za-z0-9+/=\s]+$", s[:300]):
                    b64s.append(s.replace("\n", "").replace(" ", ""))
            _walk_audio_hints(v, urls, b64s)
    elif isinstance(obj, list):
        for x in obj:
            _walk_audio_hints(x, urls, b64s)
    elif isinstance(obj, str):
        s = obj.strip()
        if s.startswith("http") and ".mp" in s.lower():
            urls.append(s)


async def _lyria_resolve_audio(
    client: httpx.AsyncClient,
    urls: list[str],
    b64s: list[str],
    trace: list[dict[str, Any]],
    api_key: str,
    http_referer: str | None,
    app_title: str,
) -> tuple[bytes | None, str | None, str | None]:
    urls = list(dict.fromkeys(urls))
    if b64s:
        try:
            audio = base64.standard_b64decode(b64s[0])
            if len(audio) > 80 * 1024 * 1024:
                return None, None, "Lyria: zdekodowany plik audio zbyt duży"
            return audio, None, None
        except Exception as exc:
            return None, None, f"Lyria: błąd base64: {exc!s:.200}"
    if urls:
        u = urls[0]
        trace.append({"provider": "openrouter_lyria", "step": 3, "GET_audio": u[:400]})
        get_kw: dict[str, Any] = {}
        if api_key and ("openrouter.ai" in u or "openrouter.com" in u):
            get_kw["headers"] = _http_headers(api_key, http_referer, app_title)
        ar = await client.get(u, follow_redirects=True, timeout=180.0, **get_kw)
        if ar.is_error:
            return None, u, f"Lyria: pobranie audio HTTP {ar.status_code}"
        return ar.content, u, None
    return None, None, None


async def fetch_lyria_audio(
    api_key: str,
    *,
    base_url: str,
    http_referer: str | None,
    app_title: str,
    body: dict[str, Any],
    timeout: float = 300.0,
) -> tuple[bytes | None, str | None, list[dict[str, Any]], str | None]:
    """Zwraca ``(audio_bytes, opcjonalny_url, trace, error)``."""
    trace: list[dict[str, Any]] = []
    root = base_url.rstrip("/")
    url = f"{root}/chat/completions"
    body_use = _lyria_ensure_audio_request(dict(body))
    body_use.pop("stream", None)
    trace.append(
        {
            "provider": "openrouter_lyria",
            "step": 1,
            "POST": url,
            "model": body_use.get("model"),
            "modalities": body_use.get("modalities"),
            "audio": body_use.get("audio"),
        },
    )
    tmo = httpx.Timeout(60.0, read=max(300.0, float(timeout)))
    headers = _http_headers(api_key, http_referer, app_title)

    async with httpx.AsyncClient(timeout=tmo) as client:
        trace.append(
            {
                "provider": "openrouter_lyria",
                "step": 2,
                "stream": True,
                "note": "OpenRouter — audio przez stream SSE.",
            },
        )
        su, sb, syn, s_err = await _lyria_stream_collect_audio(client, url, body_use, headers, float(timeout))
        if s_err:
            trace.append({"provider": "openrouter_lyria", "step": 3, "stream_warning": s_err[:1200]})
        urls, b64s = su, sb
        audio, cdn, err = await _lyria_resolve_audio(
            client, urls, b64s, trace, api_key, http_referer, app_title,
        )
        if err:
            return None, cdn, trace, err
        if audio is not None:
            return audio, cdn, trace, None
        if s_err:
            return None, None, trace, f"Lyria (SSE): {s_err[:900]}"

        data: Any = syn if isinstance(syn, dict) else {}
        raw_text = ""
        try:
            raw_text = json.dumps(data, ensure_ascii=False)[:2000]
        except Exception:
            raw_text = str(data)[:1200]

        text_only: str | None = None
        try:
            chs = data.get("choices") if isinstance(data, dict) else None
            if isinstance(chs, list) and chs and isinstance(chs[0], dict):
                msg0 = chs[0].get("message")
                mc = msg0.get("content") if isinstance(msg0, dict) else None
                if isinstance(mc, str) and len(mc) > 120 and "http" not in mc.lower():
                    text_only = (
                        "Lyria zwróciła tylko tekst — sprawdź dokumentację OpenRouter (modalities / audio)."
                    )
        except Exception:
            pass
        trace.append(
            {
                "provider": "openrouter_lyria",
                "step": 9,
                "hint": "Brak URL/base64 audio w strumieniu SSE.",
                "text_only_response": text_only,
                "response_sample": raw_text[:1200],
            },
        )
        err_msg = "Lyria: nie udało się wyciągnąć audio z odpowiedzi (zobacz trace)."
        if text_only:
            err_msg = f"{err_msg} {text_only}"
        return None, None, trace, err_msg


class OpenRouterLyriaMusicGenerator:
    """Klient Lyrii przez OpenRouter (jedna ścieżka na wywołanie ``fetch_lyria_audio``)."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str,
        model: str,
        http_referer: str | None = None,
        app_title: str = "TeacherHelper API",
        timeout: float = 300.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._http_referer = http_referer
        self._app_title = app_title
        self._timeout = float(timeout)

    async def generate(
        self,
        *,
        title: str,
        style: str,
        lyrics: str,
        instrumental: bool = False,
        variation_suffix: str = "",
    ) -> tuple[bytes | None, str | None, list[dict[str, Any]], str | None]:
        body = build_lyria_openrouter_body(
            title=title,
            style=style,
            lyrics=lyrics,
            instrumental=instrumental,
            model=self._model,
            variation_suffix=variation_suffix,
        )
        return await fetch_lyria_audio(
            self._api_key,
            base_url=self._base_url,
            http_referer=self._http_referer,
            app_title=self._app_title,
            body=body,
            timeout=self._timeout,
        )
