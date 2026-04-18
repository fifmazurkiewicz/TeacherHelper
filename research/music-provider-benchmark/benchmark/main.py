"""Minimalna aplikacja FastAPI: podgląd żądań → edycja → zatwierdzenie → /api/run."""

from __future__ import annotations

import asyncio
import base64
import re
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException, status
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from benchmark.kie import (
    KIE_STATUSES_WITH_POSSIBLE_AUDIO,
    KIE_TERMINAL_FAIL_STATUSES,
    KieClient,
    MusicSubmitRequest,
    build_kie_generate_body,
    download_audio_url,
    parse_task_record,
)
from benchmark.elevenlabs_music import build_elevenlabs_compose_body, elevenlabs_compose_raw
from benchmark.model_catalog import (
    ELEVENLABS_MUSIC_MODELS,
    KIE_SUNO_MODELS,
    OPENROUTER_VIDEO_MODELS,
    WAVESPEED_MINIMAX_VARIANTS,
    fetch_openrouter_music_model_ids,
)
from benchmark.openrouter_media import (
    build_lyria_openrouter_body,
    build_seedance_video_body,
    openrouter_lyria_raw,
    openrouter_seedance_raw,
)
from benchmark.settings import get_settings
from benchmark.wavespeed_minimax import (
    WavespeedMinimaxVariant,
    build_minimax_payload,
    wavespeed_minimax_generate_from_payload,
    wavespeed_submit_url,
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="Music provider benchmark",
    version="0.1.0",
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
)


class BenchmarkModelRow(BaseModel):
    """Wiersz konfiguracji: KIE Suno, WaveSpeed MiniMax, OpenRouter (Lyria / wideo Seedance) lub ElevenLabs Music."""

    provider: Literal[
        "kie_music",
        "wavespeed_minimax",
        "openrouter_music",
        "openrouter_video",
        "elevenlabs_music",
    ]
    model_id: str = Field(..., min_length=1, max_length=220)


class WavespeedJobItem(BaseModel):
    variant: Literal["music-02", "music-2.6"]
    wavespeed_json: dict[str, Any]


def _default_model_rows() -> list[BenchmarkModelRow]:
    """Pusta lista — użytkownik dodaje wiersze w UI („+ Dodaj model”)."""
    return []


class BenchmarkPreviewRequest(BaseModel):
    title: str = Field(default="Benchmark", max_length=80)
    style: str = Field(default="Educational pop, cheerful, classroom-friendly", max_length=2000)
    lyrics: str = Field(..., min_length=1)
    instrumental: bool = False
    kie_model: str = Field(
        default="V5",
        description="Bez wierszy «kie_music» lista «kie_jsons» w podglądzie jest pusta — to pole nie dodaje zadania KIE.",
    )
    wavespeed_minimax: Literal["music-02", "music-2.6"] = Field(
        default="music-2.6",
        description="Bez wierszy «wavespeed_minimax» lista «wavespeed_jobs» jest pusta — to pole nie dodaje zadania WaveSpeed.",
    )
    duration_minutes: float = Field(
        default=2.0,
        ge=0.05,
        le=5.0,
        description="KIE / WaveSpeed: dopisek docelowej długości w stylu lub promptcie (API bez jawnego pola minut).",
    )
    model_rows: list[BenchmarkModelRow] = Field(default_factory=_default_model_rows)


class BenchmarkPreviewResponse(BaseModel):
    """Dokładne JSON-y, które pójdą do API — do edycji w UI przed ``POST /api/run``."""

    mapping: list[dict[str, Any]]
    model_rows: list[BenchmarkModelRow]
    kie_jsons: list[dict[str, Any]]
    wavespeed_jobs: list[WavespeedJobItem]
    openrouter_music_jsons: list[dict[str, Any]]
    elevenlabs_jsons: list[dict[str, Any]]
    openrouter_seedance_jsons: list[dict[str, Any]]
    urls: dict[str, Any]


class BenchmarkExecuteRequest(BaseModel):
    """Zatwierdzone (po edycji) payloady — tylko te trafiają do dostawców."""

    kie_jsons: list[dict[str, Any]]
    wavespeed_jobs: list[WavespeedJobItem]
    openrouter_music_jsons: list[dict[str, Any]]
    elevenlabs_jsons: list[dict[str, Any]] = Field(default_factory=list)
    openrouter_seedance_jsons: list[dict[str, Any]] = Field(default_factory=list)
    kie_poll_timeout_seconds: float = Field(default=180.0, ge=30.0, le=600.0)
    wavespeed_poll_timeout_seconds: float = Field(default=240.0, ge=30.0, le=600.0)
    openrouter_seedance_poll_timeout_seconds: float = Field(default=300.0, ge=60.0, le=900.0)
    elevenlabs_timeout_seconds: float = Field(default=300.0, ge=60.0, le=900.0)


class ProviderArtifact(BaseModel):
    provider: str
    ok: bool
    filename: str
    mime_type: str = "audio/mpeg"
    base64_mp3: str | None = None
    media_url: str | None = None
    error: str | None = None
    size_bytes: int | None = None


class BenchmarkRunResponse(BaseModel):
    trace: list[dict[str, Any]]
    artifacts: list[ProviderArtifact]


def _b64(data: bytes) -> str:
    return base64.standard_b64encode(data).decode("ascii")


def _fs_slug(segment: str, max_len: int = 96) -> str:
    """Fragment nazwy pliku: bez znaków niedozwolonych w Windows."""
    s = (segment or "").strip()
    for ch in '<>:"/\\|?*\n\r\t':
        s = s.replace(ch, " ")
    s = " ".join(s.split())
    out: list[str] = []
    for c in s:
        if c.isalnum() or c in "._-":
            out.append(c)
        else:
            out.append("_")
    slug = "".join(out).strip("._")
    while "__" in slug:
        slug = slug.replace("__", "_")
    slug = slug[:max_len].strip("._")
    return slug or "track"


def _title_from_wavespeed_prompt(prompt: str) -> str:
    m = re.search(r"(?:Song title:|Title:)\s*([^.]+)", prompt, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return "track"


def _title_from_lyria_messages(ly: dict[str, Any]) -> str:
    msgs = ly.get("messages")
    if not isinstance(msgs, list) or not msgs:
        return "track"
    first = msgs[0]
    if not isinstance(first, dict):
        return "track"
    content = first.get("content")
    if isinstance(content, str):
        t = content.strip().split("\n", 1)[0]
        return (t[:120] or "track").strip()
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
                t = str(part["text"]).strip().split("\n", 1)[0]
                return (t[:120] or "track").strip()
    return "track"


def _lyria_output_ext_mime(ly: dict[str, Any] | None) -> tuple[str, str]:
    """Rozszerzenie pliku i MIME wg ``audio.format`` w żądaniu Lyrii (OpenRouter domyślnie WAV)."""
    if not isinstance(ly, dict):
        return ".wav", "audio/wav"
    aud = ly.get("audio")
    fmt = ""
    if isinstance(aud, dict):
        fmt = str(aud.get("format") or "").strip().lower()
    if fmt in ("wav", "wave", "x-wav"):
        return ".wav", "audio/wav"
    if fmt in ("mp3", "mpeg"):
        return ".mp3", "audio/mpeg"
    if fmt == "flac":
        return ".flac", "audio/flac"
    if fmt in ("aac", "m4a"):
        return ".aac", "audio/aac"
    if fmt in ("ogg", "opus"):
        return ".ogg", "audio/ogg"
    return ".wav", "audio/wav"


def _artifact_mp3_filename(
    provider_key: str,
    body: BenchmarkExecuteRequest,
    *,
    kie_json: dict[str, Any] | None = None,
    wavespeed_variant: WavespeedMinimaxVariant | None = None,
    wavespeed_json: dict[str, Any] | None = None,
    openrouter_lyria_json: dict[str, Any] | None = None,
    elevenlabs_json: dict[str, Any] | None = None,
    openrouter_seedance_json: dict[str, Any] | None = None,
) -> str:
    """Nazwa pliku artefaktu — rozszerzenie wg dostawcy (Lyria: z ``audio.format``)."""
    if provider_key == "kie":
        k = kie_json or {}
        p, model, title = "kie", str(k.get("model") or "unknown"), str(k.get("title") or "track")
    elif provider_key == "wavespeed_minimax":
        p = "wavespeed_minimax"
        ws = wavespeed_json or {}
        model = str(wavespeed_variant or "unknown")
        title = _title_from_wavespeed_prompt(str(ws.get("prompt") or ""))
    elif provider_key == "openrouter_lyria":
        ol = openrouter_lyria_json or {}
        p = "openrouter_lyria"
        model = str(ol.get("model") or "lyria")
        title = _title_from_lyria_messages(ol)
    elif provider_key == "openrouter_seedance":
        osd = openrouter_seedance_json or {}
        p = "openrouter_seedance"
        model = str(osd.get("model") or "seedance")
        title = str(osd.get("prompt") or "clip").strip()[:80] or "clip"
    elif provider_key == "elevenlabs_music":
        el = elevenlabs_json or {}
        p = "elevenlabs_music"
        model = str(el.get("model_id") or "music_v1")
        title = str(el.get("prompt") or "track").strip().split("\n", 1)[0][:120] or "track"
    else:
        p, model, title = provider_key, "unknown", "track"
    if provider_key == "openrouter_seedance":
        ext = ".mp4"
    elif provider_key == "openrouter_lyria":
        ext, _ = _lyria_output_ext_mime(openrouter_lyria_json)
    else:
        ext = ".mp3"
    return f"{_fs_slug(p, 28)}_{_fs_slug(model, 40)}_{_fs_slug(title, 100)}{ext}"


def _validate_openrouter_video_model_id(model_id: str) -> None:
    mid = (model_id or "").strip()
    if "seedance" not in mid.lower():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Model OpenRouter (wideo): oczekiwano identyfikatora Seedance, otrzymano: {mid!r}",
        )


def _validate_openrouter_music_model_id(model_id: str) -> None:
    mid = (model_id or "").strip()
    if "lyria" not in mid.lower():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Model OpenRouter (muzyka): oczekiwano identyfikatora Lyria, otrzymano: {mid!r}",
        )


def _validate_elevenlabs_music_model_id(model_id: str) -> None:
    allowed = {m["id"] for m in ELEVENLABS_MUSIC_MODELS}
    mid = (model_id or "").strip()
    if mid not in allowed:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Model ElevenLabs Music: dozwolone {sorted(allowed)}, otrzymano: {mid!r}",
        )


def _check_benchmark_key(x_benchmark_key: str | None) -> None:
    s = get_settings()
    if (s.benchmark_secret or "").strip():
        if x_benchmark_key != s.benchmark_secret.strip():
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Nagłówek X-Benchmark-Key nieprawidłowy")


def _validate_wavespeed_row_model_id(model_id: str) -> WavespeedMinimaxVariant:
    mid = (model_id or "").strip()
    if mid not in ("music-02", "music-2.6"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"WaveSpeed MiniMax: dozwolone «music-02», «music-2.6» — otrzymano: {mid!r}",
        )
    return mid  # type: ignore[return-value]


def _validate_execute(body: BenchmarkExecuteRequest) -> None:
    if not isinstance(body.kie_jsons, list):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="«kie_jsons» musi być listą")
    for i, k in enumerate(body.kie_jsons):
        if not isinstance(k, dict):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"KIE JSON [{i}]: oczekiwano obiektu")
        for key in ("prompt", "customMode", "instrumental", "model", "callBackUrl"):
            if key not in k:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"KIE JSON [{i}]: brak pola «{key}»",
                )
        if not str(k.get("callBackUrl") or "").strip():
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"KIE JSON [{i}]: «callBackUrl» nie może być pusty",
            )
    if not isinstance(body.wavespeed_jobs, list):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="«wavespeed_jobs» musi być listą")
    for i, job in enumerate(body.wavespeed_jobs):
        if not isinstance(job.wavespeed_json, dict) or not job.wavespeed_json:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"WaveSpeed [{i}]: «wavespeed_json» musi być niepustym obiektem",
            )
    if not isinstance(body.openrouter_music_jsons, list):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="OpenRouter (muzyka): «openrouter_music_jsons» musi być listą",
        )
    for i, ol in enumerate(body.openrouter_music_jsons):
        if not isinstance(ol, dict) or "model" not in ol or "messages" not in ol:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"OpenRouter muzyka [{i}]: wymagane pola «model», «messages»",
            )
        _validate_openrouter_music_model_id(str(ol.get("model") or ""))
    if not isinstance(body.elevenlabs_jsons, list):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="«elevenlabs_jsons» musi być listą")
    for i, el in enumerate(body.elevenlabs_jsons):
        if not isinstance(el, dict):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"ElevenLabs [{i}]: oczekiwano obiektu JSON")
        for key in ("model_id", "prompt", "music_length_ms"):
            if key not in el:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"ElevenLabs [{i}]: brak pola «{key}»",
                )
        _validate_elevenlabs_music_model_id(str(el.get("model_id") or ""))
    if not isinstance(body.openrouter_seedance_jsons, list):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="OpenRouter Seedance: «openrouter_seedance_jsons» musi być listą",
        )
    for i, osd in enumerate(body.openrouter_seedance_jsons):
        if not isinstance(osd, dict) or "model" not in osd or "prompt" not in osd:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"OpenRouter Seedance [{i}]: wymagane pola «model», «prompt»",
            )
        _validate_openrouter_video_model_id(str(osd.get("model") or ""))


def _build_preview(form: BenchmarkPreviewRequest, call_back_url: str) -> BenchmarkPreviewResponse:
    kie_models: list[str] = []
    ws_variants: list[WavespeedMinimaxVariant] = []
    or_ids: list[str] = []
    seed_models: list[str] = []
    el_ids: list[str] = []
    for row in form.model_rows:
        mid = row.model_id.strip()
        if row.provider == "kie_music":
            if not mid:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="KIE: pusty «model_id» w wierszu")
            kie_models.append(mid)
        elif row.provider == "wavespeed_minimax":
            ws_variants.append(_validate_wavespeed_row_model_id(mid))
        elif row.provider == "openrouter_music":
            _validate_openrouter_music_model_id(mid)
            or_ids.append(mid)
        elif row.provider == "openrouter_video":
            _validate_openrouter_video_model_id(mid)
            seed_models.append(mid)
        else:
            _validate_elevenlabs_music_model_id(mid)
            el_ids.append(mid)

    kie_jsons: list[dict[str, Any]] = []
    for km in kie_models:
        req = MusicSubmitRequest(
            prompt=form.lyrics,
            title=form.title,
            style=form.style,
            instrumental=form.instrumental,
            model=km,
            custom_mode=True,
            call_back_url=call_back_url,
            target_duration_minutes=form.duration_minutes,
        )
        try:
            kie_jsons.append(build_kie_generate_body(req))
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    wavespeed_jobs: list[WavespeedJobItem] = []
    for wv in ws_variants:
        v: WavespeedMinimaxVariant = wv
        wavespeed_jobs.append(
            WavespeedJobItem(
                variant=v,
                wavespeed_json=build_minimax_payload(
                    v,
                    style=form.style,
                    title=form.title,
                    lyrics=form.lyrics,
                    instrumental=form.instrumental,
                    duration_minutes=form.duration_minutes,
                ),
            ),
        )
    openrouter_music_jsons = [
        build_lyria_openrouter_body(
            title=form.title,
            style=form.style,
            lyrics=form.lyrics,
            instrumental=form.instrumental,
            model=mid,
        )
        for mid in or_ids
    ]
    elevenlabs_jsons = [
        build_elevenlabs_compose_body(
            title=form.title,
            style=form.style,
            lyrics=form.lyrics,
            instrumental=form.instrumental,
            model_id=mid,
            duration_minutes=form.duration_minutes,
        )
        for mid in el_ids
    ]
    openrouter_seedance_jsons = [
        build_seedance_video_body(
            title=form.title,
            style=form.style,
            lyrics=form.lyrics,
            instrumental=form.instrumental,
            model=sm,
        )
        for sm in seed_models
    ]
    s = get_settings()
    base_kie = (s.kie_api_base_url or "").strip().rstrip("/") or "https://api.kie.ai"
    base_ws = (s.wavespeed_api_base_url or "").strip().rstrip("/") or "https://api.wavespeed.ai"
    or_base = (s.openrouter_base_url or "").strip().rstrip("/") or "https://openrouter.ai/api/v1"

    mapping = [
        {"provider": "kie", "form": "title", "api": "title", "opis": "Tytuł utworu"},
        {"provider": "kie", "form": "style", "api": "style", "opis": "Gatunek / nastrój"},
        {"provider": "kie", "form": "lyrics", "api": "prompt", "opis": "Tryb custom: tekst śpiewany"},
        {"provider": "kie", "form": "instrumental", "api": "instrumental", "opis": "boolean"},
        {
            "provider": "kie",
            "form": "model_rows (kie_music)",
            "api": "model",
            "opis": (
                f"KIE Suno: {len(kie_jsons)} zadań (modele: {', '.join(str(k.get('model')) for k in kie_jsons)})"
                if kie_jsons
                else "KIE Suno: brak wierszy «kie_music» — brak zadań w podglądzie"
            ),
        },
        {
            "provider": "kie",
            "form": "duration_minutes",
            "api": "style (dopisek)",
            "opis": f"brak pola długości w API — dopisano do stylu: ~{form.duration_minutes} min",
        },
        {"provider": "wavespeed", "form": "style + title", "api": "prompt", "opis": "Opis stylu w prompt"},
        {
            "provider": "wavespeed",
            "form": "duration_minutes",
            "api": "prompt (dopisek)",
            "opis": f"wskazówka długości w tekście promptu (~{form.duration_minutes} min)",
        },
        {"provider": "wavespeed", "form": "lyrics", "api": "lyrics", "opis": "Tekst / zwrotki"},
        {
            "provider": "wavespeed",
            "form": "model_rows (wavespeed_minimax)",
            "api": "endpoint + payload",
            "opis": (
                f"WaveSpeed: {len(wavespeed_jobs)} zadań ({', '.join(j.variant for j in wavespeed_jobs)})"
                if wavespeed_jobs
                else "WaveSpeed: brak wierszy «wavespeed_minimax» — brak zadań w podglądzie"
            ),
        },
        {
            "provider": "openrouter",
            "form": "model_rows (openrouter_music) + title, style, lyrics, instrumental",
            "api": "Lyria chat/completions (lista żądań)",
            "opis": f"OpenRouter — muzyka: {len(openrouter_music_jsons)} × Lyria (modele: {', '.join(or_ids)})",
        },
        {
            "provider": "elevenlabs",
            "form": "model_rows (elevenlabs_music) + title, style, lyrics, instrumental, duration_minutes",
            "api": "POST /v1/music",
            "opis": f"ElevenLabs Music: {len(elevenlabs_jsons)} zadań" if elevenlabs_jsons else "ElevenLabs Music: brak wierszy w model_rows",
        },
        {
            "provider": "openrouter",
            "form": "model_rows (openrouter_video) + title, style, lyrics, instrumental",
            "api": "Seedance POST /videos",
            "opis": (
                f"ByteDance Seedance — {len(openrouter_seedance_jsons)} zadań (modele: {', '.join(seed_models)})"
                if openrouter_seedance_jsons
                else "ByteDance Seedance — brak wierszy «openrouter_video» w model_rows"
            ),
        },
    ]

    ws_posts = {
        "music-2.6": wavespeed_submit_url(base_ws, "music-2.6"),
        "music-02": wavespeed_submit_url(base_ws, "music-02"),
    }
    return BenchmarkPreviewResponse(
        mapping=mapping,
        model_rows=list(form.model_rows),
        kie_jsons=kie_jsons,
        wavespeed_jobs=wavespeed_jobs,
        openrouter_music_jsons=openrouter_music_jsons,
        elevenlabs_jsons=elevenlabs_jsons,
        openrouter_seedance_jsons=openrouter_seedance_jsons,
        urls={
            "kie_post": f"{base_kie}/api/v1/generate",
            "kie_poll": f"{base_kie}/api/v1/generate/record-info?taskId=<taskId>",
            "wavespeed_post_by_variant": ws_posts,
            "wavespeed_poll": f"{base_ws}/api/v3/predictions/<predictionId>/result",
            "openrouter_lyria_post": f"{or_base}/chat/completions",
            "openrouter_seedance_post": f"{or_base}/videos",
            "elevenlabs_music_post": f"{(s.elevenlabs_api_base_url or '').strip().rstrip('/') or 'https://api.elevenlabs.io'}/v1/music",
        },
    )


class ModelCatalogResponse(BaseModel):
    kie_music: list[dict[str, str]]
    wavespeed_minimax: list[dict[str, str]]
    openrouter_music: list[dict[str, str]]
    openrouter_video: list[dict[str, str]]
    elevenlabs_music: list[dict[str, str]]


@app.get("/api/model-catalog", response_model=ModelCatalogResponse)
async def api_model_catalog(
    x_benchmark_key: str | None = Header(default=None, alias="X-Benchmark-Key"),
) -> ModelCatalogResponse:
    """Listy modeli do UI: KIE Suno, WaveSpeed MiniMax, OpenRouter Lyria (max 10), OpenRouter wideo (Seedance), ElevenLabs Music."""
    _check_benchmark_key(x_benchmark_key)
    s = get_settings()
    or_models = await fetch_openrouter_music_model_ids(
        api_key=(s.openrouter_api_key or "").strip() or None,
        base_url=s.openrouter_base_url,
    )
    return ModelCatalogResponse(
        kie_music=list(KIE_SUNO_MODELS),
        wavespeed_minimax=list(WAVESPEED_MINIMAX_VARIANTS),
        openrouter_music=or_models,
        openrouter_video=list(OPENROUTER_VIDEO_MODELS),
        elevenlabs_music=list(ELEVENLABS_MUSIC_MODELS),
    )


@app.post("/api/preview", response_model=BenchmarkPreviewResponse)
async def api_preview(
    form: BenchmarkPreviewRequest,
    x_benchmark_key: str | None = Header(default=None, alias="X-Benchmark-Key"),
) -> BenchmarkPreviewResponse:
    """Buduje JSON-y **bez** wywołań do zewnętrznych API — do edycji i potwierdzenia."""
    _check_benchmark_key(x_benchmark_key)
    s = get_settings()
    cb = (s.kie_music_callback_url or "").strip()
    if any(r.provider == "kie_music" for r in form.model_rows) and not cb:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Brak KIE_MUSIC_CALLBACK_URL w .env (są wiersze KIE — Suno)",
        )
    return _build_preview(form, cb)


async def _run_kie_raw_trace(
    *,
    client: KieClient,
    kie_json: dict[str, Any],
    poll_timeout: float,
    poll_interval: float,
) -> tuple[bytes | None, list[dict[str, Any]], str | None]:
    trace: list[dict[str, Any]] = []
    trace.append(
        {
            "provider": "kie",
            "step": 1,
            "description": "POST https://api.kie.ai/api/v1/generate (zatwierdzony JSON)",
            "headers": {"Authorization": "Bearer ***", "Content-Type": "application/json"},
            "json_body": kie_json,
        },
    )
    sub = await client.submit_raw(kie_json)
    trace.append(
        {
            "provider": "kie",
            "step": 2,
            "description": "Odpowiedź submit",
            "ok": sub.ok,
            "http_status": sub.http_status,
            "task_id": sub.task_id,
            "error_detail": sub.error_detail,
            "payload_excerpt": {k: sub.payload.get(k) for k in ("code", "msg", "data") if isinstance(sub.payload, dict)},
        },
    )
    if not sub.ok or not sub.task_id:
        return None, trace, sub.error_detail or "KIE submit nieudany"

    deadline = time.monotonic() + poll_timeout
    interval = max(0.35, poll_interval)
    last_st: str | None = None
    poll_n = 0
    while time.monotonic() < deadline:
        poll_n += 1
        rec = await client.fetch_task_record(sub.task_id)
        st, urls, perr = parse_task_record(rec)
        last_st = st
        if poll_n <= 3 or st in KIE_STATUSES_WITH_POSSIBLE_AUDIO or st in KIE_TERMINAL_FAIL_STATUSES:
            trace.append(
                {
                    "provider": "kie",
                    "step": 2 + poll_n,
                    "description": "GET /api/v1/generate/record-info",
                    "query": {"taskId": sub.task_id},
                    "status": st,
                    "audio_urls_count": len(urls),
                    "terminal_error": perr,
                },
            )
        if urls and st in KIE_STATUSES_WITH_POSSIBLE_AUDIO:
            try:
                mp3 = await download_audio_url(urls[0])
            except Exception as exc:
                return None, trace, f"Pobranie MP3: {exc!s:.400}"
            trace.append(
                {
                    "provider": "kie",
                    "step": 2 + poll_n + 1,
                    "description": "GET pierwszego audioUrl",
                    "url": urls[0][:200] + ("…" if len(urls[0]) > 200 else ""),
                },
            )
            return mp3, trace, None
        if st in KIE_TERMINAL_FAIL_STATUSES:
            return None, trace, perr or st or "KIE błąd terminalny"
        await asyncio.sleep(interval)

    return None, trace, f"Timeout KIE po {int(poll_timeout)} s (ostatni status: {last_st!r})"


@app.post("/api/run", response_model=BenchmarkRunResponse)
async def api_run(
    body: BenchmarkExecuteRequest,
    x_benchmark_key: str | None = Header(default=None, alias="X-Benchmark-Key"),
) -> BenchmarkRunResponse:
    """Wysyła **dokładnie** przekazane JSON-y (po edycji i zatwierdzeniu w UI)."""
    _check_benchmark_key(x_benchmark_key)
    _validate_execute(body)

    s = get_settings()
    if body.kie_jsons and not (s.kie_api_key or "").strip():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Brak KIE_API_KEY")
    ws_key = (s.wavespeed_api_key or "").strip()
    if body.wavespeed_jobs and not ws_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Brak WAVESPEED_API_KEY")

    trace: list[dict[str, Any]] = [
        {
            "step": 1,
            "description": "Wykonanie — zatwierdzone payloady (bez ponownego mapowania z formularza)",
            "kie_jobs": len(body.kie_jsons),
            "wavespeed_jobs": len(body.wavespeed_jobs),
            "openrouter_music_jobs": len(body.openrouter_music_jsons),
            "elevenlabs_jobs": len(body.elevenlabs_jsons),
            "openrouter_seedance_jobs": len(body.openrouter_seedance_jsons),
        },
    ]

    kie_client = KieClient(s.kie_api_key.strip(), s.kie_api_base_url.strip() or "https://api.kie.ai") if body.kie_jsons else None
    or_key = (s.openrouter_api_key or "").strip()
    or_base = (s.openrouter_base_url or "").strip() or "https://openrouter.ai/api/v1"
    or_ref = (s.openrouter_http_referer or "").strip() or None
    el_key = (s.elevenlabs_api_key or "").strip()
    el_base = (s.elevenlabs_api_base_url or "").strip().rstrip("/") or "https://api.elevenlabs.io"

    async def job_kie_one(
        kie_json: dict[str, Any],
    ) -> tuple[str, dict[str, Any], bytes | None, list[dict[str, Any]], str | None, str | None]:
        assert kie_client is not None
        mp3, tr, err = await _run_kie_raw_trace(
            client=kie_client,
            kie_json=kie_json,
            poll_timeout=body.kie_poll_timeout_seconds,
            poll_interval=s.kie_music_poll_interval_seconds,
        )
        return "kie", {"kie_json": kie_json}, mp3, tr, err, None

    async def job_ws_one(
        job: WavespeedJobItem,
    ) -> tuple[str, dict[str, Any], bytes | None, list[dict[str, Any]], str | None, str | None]:
        v: WavespeedMinimaxVariant = job.variant
        mp3, tr, err = await wavespeed_minimax_generate_from_payload(
            ws_key,
            base_url=s.wavespeed_api_base_url,
            variant=v,
            payload=job.wavespeed_json,
            poll_timeout=body.wavespeed_poll_timeout_seconds,
        )
        return "wavespeed_minimax", {"variant": v, "wavespeed_json": job.wavespeed_json}, mp3, tr, err, None

    async def job_lyria_one(
        ly_body: dict[str, Any],
    ) -> tuple[str, dict[str, Any], bytes | None, list[dict[str, Any]], str | None, str | None]:
        if not or_key:
            return "openrouter_lyria", {"ly": ly_body}, None, [], "Brak OPENROUTER_API_KEY w .env", None
        mp3, url, tr, err = await openrouter_lyria_raw(
            or_key,
            base_url=or_base,
            http_referer=or_ref,
            body=ly_body,
        )
        return "openrouter_lyria", {"ly": ly_body}, mp3, tr, err, url

    async def job_seedance_one(
        seed_body: dict[str, Any],
    ) -> tuple[str, dict[str, Any], bytes | None, list[dict[str, Any]], str | None, str | None]:
        if not or_key:
            return "openrouter_seedance", {"seed": seed_body}, None, [], "Brak OPENROUTER_API_KEY w .env", None
        vid, url, tr, err = await openrouter_seedance_raw(
            or_key,
            base_url=or_base,
            http_referer=or_ref,
            body=seed_body,
            poll_timeout=body.openrouter_seedance_poll_timeout_seconds,
        )
        return "openrouter_seedance", {"seed": seed_body}, vid, tr, err, url

    async def job_elevenlabs_one(
        el_body: dict[str, Any],
    ) -> tuple[str, dict[str, Any], bytes | None, list[dict[str, Any]], str | None, str | None]:
        if not el_key:
            return "elevenlabs_music", {"el": el_body}, None, [], "Brak ELEVENLABS_API_KEY w .env", None
        mp3, tr, err = await elevenlabs_compose_raw(
            el_key,
            base_url=el_base,
            body=el_body,
            timeout=body.elevenlabs_timeout_seconds,
        )
        return "elevenlabs_music", {"el": el_body}, mp3, tr, err, None

    coros: list[Any] = []
    if kie_client:
        for kj in body.kie_jsons:
            coros.append(job_kie_one(kj))
    for wj in body.wavespeed_jobs:
        coros.append(job_ws_one(wj))
    for ly in body.openrouter_music_jsons:
        coros.append(job_lyria_one(ly))
    for sd in body.openrouter_seedance_jsons:
        coros.append(job_seedance_one(sd))
    for el in body.elevenlabs_jsons:
        coros.append(job_elevenlabs_one(el))

    results = await asyncio.gather(*coros, return_exceptions=True)
    artifacts: list[ProviderArtifact] = []
    max_raw_for_b64 = 10 * 1024 * 1024

    for item in results:
        if isinstance(item, Exception):
            trace.append({"provider": "?", "error": repr(item)})
            continue
        name, meta, mp3, tr, err, extra_url = item
        trace.extend([{**row, "parallel_job": name} if isinstance(row, dict) else row for row in tr])
        fname = _artifact_mp3_filename(
            name,
            body,
            kie_json=meta.get("kie_json"),
            wavespeed_variant=meta.get("variant"),
            wavespeed_json=meta.get("wavespeed_json"),
            openrouter_lyria_json=meta.get("ly"),
            elevenlabs_json=meta.get("el"),
            openrouter_seedance_json=meta.get("seed"),
        )
        if name == "openrouter_seedance":
            mime = "video/mp4"
        elif name == "openrouter_lyria":
            _, mime = _lyria_output_ext_mime(meta.get("ly"))
        else:
            mime = "audio/mpeg"
        media_url = extra_url if (extra_url and name.startswith("openrouter")) else None
        prov_label = name
        if name == "kie" and meta.get("kie_json"):
            prov_label = f"kie:{meta['kie_json'].get('model')}"
        elif name == "wavespeed_minimax" and meta.get("variant"):
            prov_label = f"{name}:{meta.get('variant')}"
        elif name == "openrouter_lyria" and meta.get("ly"):
            prov_label = f"{name}:{meta['ly'].get('model')}"
        elif name == "elevenlabs_music" and meta.get("el"):
            prov_label = f"{name}:{meta['el'].get('model_id')}"
        elif name == "openrouter_seedance" and meta.get("seed"):
            prov_label = f"{name}:{meta['seed'].get('model')}"

        if err:
            artifacts.append(
                ProviderArtifact(
                    provider=prov_label,
                    ok=False,
                    filename=fname,
                    mime_type=mime,
                    media_url=media_url,
                    base64_mp3=None,
                    error=err,
                ),
            )
            continue
        if mp3 and len(mp3) > max_raw_for_b64:
            artifacts.append(
                ProviderArtifact(
                    provider=prov_label,
                    ok=False,
                    filename=fname,
                    mime_type=mime,
                    media_url=media_url,
                    error=f"Plik {len(mp3)} B > limit {max_raw_for_b64} B (w trace może być link)",
                    size_bytes=len(mp3),
                ),
            )
            continue
        if mp3:
            artifacts.append(
                ProviderArtifact(
                    provider=prov_label,
                    ok=True,
                    filename=fname,
                    mime_type=mime,
                    base64_mp3=_b64(mp3),
                    media_url=media_url,
                    size_bytes=len(mp3),
                ),
            )
            continue
        if media_url and name.startswith("openrouter"):
            artifacts.append(
                ProviderArtifact(
                    provider=prov_label,
                    ok=True,
                    filename=fname,
                    mime_type=mime,
                    media_url=media_url,
                    size_bytes=None,
                ),
            )
            continue
        artifacts.append(
            ProviderArtifact(
                provider=prov_label,
                ok=False,
                filename=fname,
                mime_type=mime,
                media_url=media_url,
                base64_mp3=None,
                error="brak danych",
            ),
        )

    return BenchmarkRunResponse(trace=trace, artifacts=artifacts)


if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
