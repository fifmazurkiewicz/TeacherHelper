"""OpenRouter: Google Lyria 3 Pro (muzyka, chat/completions) i ByteDance Seedance 1.5 Pro (wideo)."""

from __future__ import annotations

import asyncio
import base64
import json
import re
import time
from typing import Any
import httpx

LYRIA_MODEL = "google/lyria-3-pro-preview"
SEEDANCE_MODEL = "bytedance/seedance-1-5-pro"


def build_lyria_openrouter_body(
    *,
    title: str,
    style: str,
    lyrics: str,
    instrumental: bool,
    model: str | None = None,
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
    mid = (model or "").strip() or LYRIA_MODEL
    # OpenRouter: wyjście audio wymaga ``modalities`` + ``audio`` (patrz multimodal / audio w dokumentacji OR).
    return {
        "model": mid,
        "messages": [{"role": "user", "content": [{"type": "text", "text": text}]}],
        "modalities": ["text", "audio"],
        "audio": {"format": "wav"},
    }


def build_seedance_video_body(
    *,
    title: str,
    style: str,
    lyrics: str,
    instrumental: bool,
    model: str | None = None,
) -> dict[str, Any]:
    ti = (title or "").strip() or "Scene"
    st = (style or "").strip() or "cinematic"
    ly = (lyrics or "").strip()
    if instrumental:
        prompt = f"Short audio-visual clip. Title: {ti}. Visual and musical mood: {st}. No dialogue, instrumental mood only."
    else:
        prompt = f"Short audio-visual clip with lip-sync friendly presentation. Title: {ti}. Mood: {st}. Theme: {ly[:2500]}"
    mid = (model or "").strip() or SEEDANCE_MODEL
    return {"model": mid, "prompt": prompt[:8000]}


def _lyria_ensure_audio_request(body: dict[str, Any]) -> dict[str, Any]:
    """Uzupełnia pola wymagane przez OpenRouter do zwrócenia audio (zamiast samego tekstu / napisów)."""
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


async def _lyria_stream_collect_audio(
    client: httpx.AsyncClient,
    url: str,
    base_body: dict[str, Any],
    headers: dict[str, str],
    read_timeout: float,
) -> tuple[list[str], list[str], dict[str, Any] | None, str | None]:
    """``POST`` ze ``stream: true`` — zbiera URL/base64 z chunków SSE i składa syntetyczną wiadomość do dalszego parsowania."""
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


def _headers(api_key: str, referer: str | None) -> dict[str, str]:
    h: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if referer:
        h["HTTP-Referer"] = referer.strip()
    h["X-Title"] = "music-provider-benchmark"
    return h


def _lyria_extra_urls_and_b64(data: Any) -> tuple[list[str], list[str]]:
    """Lyria przez OpenRouter: audio bywa w ``choices[].message.content`` (lista części), nie tylko w płaskim JSON."""
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


def _seedance_completed_media_urls(blob: dict[str, Any]) -> list[str]:
    """Po ``completed`` OpenRouter zwraca m.in. ``unsigned_urls`` (endpoint ``/content``), nie ``.mp4`` w ścieżce."""
    out: list[str] = []

    def take(val: Any) -> None:
        if isinstance(val, str) and val.startswith("http"):
            out.append(val.strip())
        elif isinstance(val, list):
            for x in val:
                if isinstance(x, str) and x.startswith("http"):
                    out.append(x.strip())

    take(blob.get("unsigned_urls"))
    take(blob.get("signed_urls"))
    take(blob.get("urls"))
    take(blob.get("output_urls"))
    for key in ("url", "video_url", "result_url", "download_url", "file_url", "output_url"):
        v = blob.get(key)
        if isinstance(v, str) and v.startswith("http"):
            out.append(v.strip())
    nested = blob.get("data") or blob.get("result")
    if isinstance(nested, dict):
        out.extend(_seedance_completed_media_urls(nested))
    return list(dict.fromkeys(out))


def _walk_audio_hints(obj: Any, urls: list[str], b64s: list[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = str(k).lower()
            if isinstance(v, str):
                s = v.strip()
                if s.startswith("http") and any(
                    s.split("?", 1)[0].lower().endswith(ext) for ext in (".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac")
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


def _walk_mp4_urls(obj: Any, out: list[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and v.startswith("http") and (".mp4" in v.lower() or "video" in k.lower()):
                out.append(v)
            _walk_mp4_urls(v, out)
    elif isinstance(obj, list):
        for x in obj:
            _walk_mp4_urls(x, out)


def _resolve_poll_url(api_v1_root: str, poll: str | None) -> str | None:
    if not poll:
        return None
    p = str(poll).strip()
    if p.startswith("http"):
        return p
    origin = re.sub(r"/api/v1/?$", "", api_v1_root.rstrip("/"))
    if p.startswith("/"):
        return origin + p
    return f"{api_v1_root.rstrip('/')}/{p.lstrip('/')}"


async def _lyria_resolve_audio(
    client: httpx.AsyncClient,
    urls: list[str],
    b64s: list[str],
    trace: list[dict[str, Any]],
    api_key: str,
    http_referer: str | None,
) -> tuple[bytes | None, str | None, str | None]:
    """Z list URL/base64 zwraca ``(bytes, url, error)``."""
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
            get_kw["headers"] = _headers(api_key, http_referer)
        ar = await client.get(u, follow_redirects=True, timeout=180.0, **get_kw)
        if ar.is_error:
            return None, u, f"Lyria: pobranie audio HTTP {ar.status_code}"
        return ar.content, u, None
    return None, None, None


async def openrouter_lyria_raw(
    api_key: str,
    *,
    base_url: str,
    http_referer: str | None,
    body: dict[str, Any],
    timeout: float = 300.0,
) -> tuple[bytes | None, str | None, list[dict[str, Any]], str | None]:
    """``(audio_bytes, optional_cdn_url, trace, error)``."""
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
    headers = _headers(api_key, http_referer)

    async with httpx.AsyncClient(timeout=tmo) as client:
        trace.append(
            {
                "provider": "openrouter_lyria",
                "step": 2,
                "stream": True,
                "note": "OpenRouter zwraca 400 przy stream:false + audio — używany jest wyłącznie POST z stream:true (SSE).",
            },
        )
        su, sb, syn, s_err = await _lyria_stream_collect_audio(client, url, body_use, headers, float(timeout))
        if s_err:
            trace.append({"provider": "openrouter_lyria", "step": 3, "stream_warning": s_err[:1200]})
        urls, b64s = su, sb
        audio, cdn, err = await _lyria_resolve_audio(client, urls, b64s, trace, api_key, http_referer)
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
                        "Lyria nadal zwraca tylko tekst (np. napisy) — sprawdź na openrouter.ai/docs "
                        "(multimodal / audio), czy model wymaga innego formatu lub limitów."
                    )
        except Exception:
            pass
        trace.append(
            {
                "provider": "openrouter_lyria",
                "step": 9,
                "hint": "Brak URL/base64 audio w strumieniu SSE (modalities + audio).",
                "text_only_response": text_only,
                "response_sample": raw_text[:1200],
            },
        )
        err = "Lyria: nie udało się wyciągnąć audio z odpowiedzi (zobacz trace)."
        if text_only:
            err = f"{err} {text_only}"
        return None, None, trace, err


async def openrouter_seedance_raw(
    api_key: str,
    *,
    base_url: str,
    http_referer: str | None,
    body: dict[str, Any],
    poll_timeout: float = 300.0,
    poll_interval: float = 2.0,
) -> tuple[bytes | None, str | None, list[dict[str, Any]], str | None]:
    """POST ``/videos`` + polling. Zwraca ``(mp4_bytes_or_none, video_url, trace, error)``."""
    trace: list[dict[str, Any]] = []
    root = base_url.rstrip("/")
    video_url = f"{root}/videos"
    trace.append({"provider": "openrouter_seedance", "step": 1, "POST": video_url, "model": body.get("model")})
    tmo = httpx.Timeout(60.0, read=600.0)
    async with httpx.AsyncClient(timeout=tmo) as client:
        r = await client.post(video_url, json=body, headers=_headers(api_key, http_referer))
        raw = r.text or ""
        try:
            start = r.json()
        except Exception:
            start = {}
        trace.append(
            {
                "provider": "openrouter_seedance",
                "step": 2,
                "http_status": r.status_code,
                "keys": list(start.keys()) if isinstance(start, dict) else None,
            },
        )
        if r.is_error:
            return None, None, trace, f"OpenRouter Seedance HTTP {r.status_code}: {raw[:900]}"
        if not isinstance(start, dict):
            return None, None, trace, "Seedance: niepoprawna odpowiedź JSON po submit"
        poll_raw = start.get("polling_url") or start.get("url") or start.get("status_url")
        poll_u = _resolve_poll_url(root, str(poll_raw) if poll_raw else None)
        if not poll_u:
            return None, None, trace, f"Seedance: brak polling_url w odpowiedzi: {raw[:600]}"
        trace.append({"provider": "openrouter_seedance", "step": 3, "poll": poll_u[:500]})
        deadline = time.monotonic() + poll_timeout
        last_blob: dict[str, Any] = {}
        while time.monotonic() < deadline:
            pr = await client.get(poll_u, headers=_headers(api_key, http_referer))
            try:
                pdata: Any = pr.json()
            except Exception:
                pdata = {}
            last_blob = pdata if isinstance(pdata, dict) else {}
            st = None
            if isinstance(pdata, dict):
                st = pdata.get("status") or pdata.get("state")
                d = pdata.get("data")
                if isinstance(d, dict):
                    st = st or d.get("status") or d.get("state")
            st_s = str(st or "").lower()
            if st_s in ("completed", "succeeded", "success", "done"):
                mp4s: list[str] = []
                if isinstance(pdata, dict):
                    mp4s.extend(_seedance_completed_media_urls(pdata))
                _walk_mp4_urls(pdata, mp4s)
                mp4s = list(dict.fromkeys(mp4s))
                if not mp4s and isinstance(pdata, dict):
                    u = pdata.get("url") or pdata.get("video_url")
                    if isinstance(u, str) and u.startswith("http"):
                        mp4s.append(u)
                if mp4s:
                    vu = mp4s[0]
                    trace.append({"provider": "openrouter_seedance", "step": 4, "video_url": vu[:500]})
                    get_kw: dict[str, Any] = {}
                    if api_key and ("openrouter.ai" in vu or "/api/v1/" in vu):
                        get_kw["headers"] = _headers(api_key, http_referer)
                    vr = await client.get(vu, follow_redirects=True, timeout=300.0, **get_kw)
                    if vr.is_error:
                        return None, vu, trace, f"Seedance: pobranie MP4 HTTP {vr.status_code}"
                    content = vr.content
                    if len(content) > 40 * 1024 * 1024:
                        return None, vu, trace, None
                    return content, vu, trace, None
                return None, None, trace, f"Seedance: status OK, brak URL wideo w JSON: {str(pdata)[:800]}"
            if st_s in ("failed", "error", "cancelled", "canceled"):
                err = ""
                if isinstance(pdata, dict):
                    err = str(pdata.get("error") or pdata.get("message") or "")
                return None, None, trace, err or f"Seedance: zadanie nieudane (status={st!r})"
            await asyncio.sleep(poll_interval)

        return None, None, trace, f"Seedance: timeout po {int(poll_timeout)} s (ostatni: {last_blob})"
