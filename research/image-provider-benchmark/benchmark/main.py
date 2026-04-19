"""FastAPI: podgląd JSON → edycja → równoległe wywołania OpenAI / Stability / OpenRouter."""

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

from benchmark.model_catalog import (
    OPENAI_IMAGE_MODELS,
    STABILITY_IMAGE_SERVICES,
    fetch_openrouter_image_model_ids,
)
from benchmark.openai_images import openai_images_generate_raw
from benchmark.openrouter_images import build_openrouter_image_body, openrouter_image_raw
from benchmark.settings import get_settings
from benchmark.stability_images import ALLOWED_STABILITY_SERVICES, stability_generate_raw

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="Image provider benchmark",
    version="0.1.0",
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
)


class BenchmarkModelRow(BaseModel):
    provider: Literal["openai_image", "stability_image", "openrouter_image"]
    model_id: str = Field(..., min_length=1, max_length=220)


class StabilityJobItem(BaseModel):
    service: str = Field(..., min_length=1, max_length=64)
    stability_form: dict[str, Any]


def _default_model_rows() -> list[BenchmarkModelRow]:
    return []


class BenchmarkPreviewRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    negative_prompt: str = Field(default="", max_length=4000)
    dall_e_size: Literal["1024x1024", "1024x1792", "1792x1024", "512x512", "256x256"] = "1024x1024"
    dall_e_quality: Literal["standard", "hd"] = "standard"
    stability_output_format: Literal["png", "webp", "jpeg"] = "png"
    stability_aspect_ratio: str = Field(default="1:1", max_length=16)
    openrouter_aspect_ratio: str | None = Field(default="1:1", max_length=16)
    openrouter_image_size: str | None = Field(default="1K", max_length=8)
    model_rows: list[BenchmarkModelRow] = Field(default_factory=_default_model_rows)


class BenchmarkPreviewResponse(BaseModel):
    mapping: list[dict[str, Any]]
    model_rows: list[BenchmarkModelRow]
    openai_jsons: list[dict[str, Any]]
    stability_jobs: list[StabilityJobItem]
    openrouter_image_jsons: list[dict[str, Any]]
    urls: dict[str, Any]


class BenchmarkExecuteRequest(BaseModel):
    openai_jsons: list[dict[str, Any]] = Field(default_factory=list)
    stability_jobs: list[StabilityJobItem] = Field(default_factory=list)
    openrouter_image_jsons: list[dict[str, Any]] = Field(default_factory=list)
    openai_timeout_seconds: float = Field(default=120.0, ge=30.0, le=600.0)
    stability_timeout_seconds: float = Field(default=180.0, ge=30.0, le=900.0)
    openrouter_timeout_seconds: float = Field(default=180.0, ge=30.0, le=900.0)


class ProviderArtifact(BaseModel):
    provider: str
    ok: bool
    filename: str
    mime_type: str = "image/png"
    base64_image: str | None = None
    media_url: str | None = None
    error: str | None = None
    size_bytes: int | None = None


class BenchmarkRunResponse(BaseModel):
    trace: list[dict[str, Any]]
    artifacts: list[ProviderArtifact]


def _b64(data: bytes) -> str:
    return base64.standard_b64encode(data).decode("ascii")


def _fs_slug(segment: str, max_len: int = 96) -> str:
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
    return slug or "image"


def _slug_from_prompt(prompt: str) -> str:
    line = (prompt or "").strip().split("\n", 1)[0]
    return _fs_slug(line, 80)


def _openai_allowed_models() -> set[str]:
    return {m["id"] for m in OPENAI_IMAGE_MODELS}


def _validate_openai_execute(j: dict[str, Any], idx: int) -> None:
    for key in ("model", "prompt"):
        if key not in j:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"OpenAI [{idx}]: wymagane «{key}»",
            )
    mid = str(j.get("model") or "")
    if mid not in _openai_allowed_models():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"OpenAI [{idx}]: model {mid!r} — dozwolone {_openai_allowed_models()}",
        )


def _validate_stability_execute(job: StabilityJobItem, idx: int) -> None:
    svc = (job.service or "").strip().lower()
    if svc not in ALLOWED_STABILITY_SERVICES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Stability [{idx}]: usługa {svc!r} — dozwolone {sorted(ALLOWED_STABILITY_SERVICES)}",
        )
    f = job.stability_form
    if not isinstance(f, dict) or "prompt" not in f:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Stability [{idx}]: «stability_form» musi zawierać «prompt»",
        )


def _validate_openrouter_execute(j: dict[str, Any], idx: int) -> None:
    if not isinstance(j, dict) or "model" not in j or "messages" not in j:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"OpenRouter obraz [{idx}]: wymagane «model», «messages»",
        )


def _validate_execute(body: BenchmarkExecuteRequest) -> None:
    for i, oj in enumerate(body.openai_jsons):
        if not isinstance(oj, dict):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"OpenAI [{i}]: oczekiwano obiektu JSON")
        _validate_openai_execute(oj, i)
    for i, sj in enumerate(body.stability_jobs):
        _validate_stability_execute(sj, i)
    for i, oi in enumerate(body.openrouter_image_jsons):
        if not isinstance(oi, dict):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"OpenRouter [{i}]: oczekiwano obiektu JSON",
            )
        _validate_openrouter_execute(oi, i)


def _check_benchmark_key(x_benchmark_key: str | None) -> None:
    s = get_settings()
    if (s.benchmark_secret or "").strip():
        if x_benchmark_key != s.benchmark_secret.strip():
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Nagłówek X-Benchmark-Key nieprawidłowy")


def _build_openai_body(
    *,
    model: str,
    prompt: str,
    size: str,
    quality: str,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "response_format": "b64_json",
    }
    if model.strip() == "dall-e-3":
        body["quality"] = quality
    return body


def _mime_from_format(fmt: str) -> str:
    f = (fmt or "png").lower().strip()
    if f in ("jpeg", "jpg"):
        return "image/jpeg"
    if f == "webp":
        return "image/webp"
    return "image/png"


def _build_preview(form: BenchmarkPreviewRequest) -> BenchmarkPreviewResponse:
    openai_models: list[str] = []
    stability_services: list[str] = []
    or_models: list[str] = []
    for row in form.model_rows:
        mid = row.model_id.strip()
        if not mid:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Pusty «model_id» w wierszu")
        if row.provider == "openai_image":
            if mid not in _openai_allowed_models():
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"OpenAI: nieznany model {mid!r} — dozwolone {_openai_allowed_models()}",
                )
            openai_models.append(mid)
        elif row.provider == "stability_image":
            if mid.lower() not in ALLOWED_STABILITY_SERVICES:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Stability: usługa {mid!r} — dozwolone {sorted(ALLOWED_STABILITY_SERVICES)}",
                )
            stability_services.append(mid.lower())
        else:
            or_models.append(mid)

    openai_jsons = [
        _build_openai_body(
            model=m,
            prompt=form.prompt,
            size=form.dall_e_size,
            quality=form.dall_e_quality,
        )
        for m in openai_models
    ]

    stability_jobs: list[StabilityJobItem] = []
    for svc in stability_services:
        sf: dict[str, Any] = {
            "prompt": form.prompt,
            "output_format": form.stability_output_format,
            "aspect_ratio": form.stability_aspect_ratio,
        }
        if (form.negative_prompt or "").strip():
            sf["negative_prompt"] = form.negative_prompt.strip()
        stability_jobs.append(StabilityJobItem(service=svc, stability_form=sf))

    or_ar = (form.openrouter_aspect_ratio or "").strip() or None
    or_sz = (form.openrouter_image_size or "").strip() or None
    openrouter_image_jsons = [
        build_openrouter_image_body(
            prompt=form.prompt,
            model=mid,
            aspect_ratio=or_ar,
            image_size=or_sz,
        )
        for mid in or_models
    ]

    s = get_settings()
    oa = (s.openai_api_base_url or "").strip().rstrip("/") or "https://api.openai.com"
    st = (s.stability_api_base_url or "").strip().rstrip("/") or "https://api.stability.ai"
    or_base = (s.openrouter_base_url or "").strip().rstrip("/") or "https://openrouter.ai/api/v1"

    mapping = [
        {"provider": "openai", "form": "prompt", "api": "prompt", "opis": "Tekst → obraz (DALL·E)"},
        {"provider": "openai", "form": "dall_e_size, dall_e_quality", "api": "size, quality", "opis": "DALL·E 3: quality; DALL·E 2: tylko size"},
        {
            "provider": "openai",
            "form": "model_rows (openai_image)",
            "api": "model",
            "opis": (
                f"OpenAI: {len(openai_jsons)} zadań ({', '.join(openai_models)})"
                if openai_jsons
                else "OpenAI: brak wierszy — brak zadań"
            ),
        },
        {"provider": "stability", "form": "prompt + negative_prompt", "api": "multipart", "opis": "Stable Image v2beta"},
        {
            "provider": "stability",
            "form": "model_rows (stability_image)",
            "api": "generate/{core|ultra|sd3}",
            "opis": (
                f"Stability: {len(stability_jobs)} zadań ({', '.join(stability_services)})"
                if stability_jobs
                else "Stability: brak wierszy"
            ),
        },
        {
            "provider": "openrouter",
            "form": "prompt + openrouter_aspect_ratio + openrouter_image_size",
            "api": "chat/completions + modalities",
            "opis": f"OpenRouter: {len(openrouter_image_jsons)} zadań" if openrouter_image_jsons else "OpenRouter: brak wierszy",
        },
    ]

    return BenchmarkPreviewResponse(
        mapping=mapping,
        model_rows=list(form.model_rows),
        openai_jsons=openai_jsons,
        stability_jobs=stability_jobs,
        openrouter_image_jsons=openrouter_image_jsons,
        urls={
            "openai_post": f"{oa}/v1/images/generations",
            "stability_post_template": f"{st}/v2beta/stable-image/generate/{{core|ultra|sd3}}",
            "openrouter_post": f"{or_base}/chat/completions",
            "openrouter_models_query": f"{or_base}/models?output_modalities=image",
        },
    )


class ModelCatalogResponse(BaseModel):
    openai_image: list[dict[str, str]]
    stability_image: list[dict[str, str]]
    openrouter_image: list[dict[str, str]]


@app.get("/api/model-catalog", response_model=ModelCatalogResponse)
async def api_model_catalog(
    x_benchmark_key: str | None = Header(default=None, alias="X-Benchmark-Key"),
) -> ModelCatalogResponse:
    _check_benchmark_key(x_benchmark_key)
    s = get_settings()
    or_models = await fetch_openrouter_image_model_ids(
        api_key=(s.openrouter_api_key or "").strip() or None,
        base_url=s.openrouter_base_url,
    )
    return ModelCatalogResponse(
        openai_image=list(OPENAI_IMAGE_MODELS),
        stability_image=list(STABILITY_IMAGE_SERVICES),
        openrouter_image=or_models,
    )


@app.post("/api/preview", response_model=BenchmarkPreviewResponse)
async def api_preview(
    form: BenchmarkPreviewRequest,
    x_benchmark_key: str | None = Header(default=None, alias="X-Benchmark-Key"),
) -> BenchmarkPreviewResponse:
    _check_benchmark_key(x_benchmark_key)
    return _build_preview(form)


def _filename_for_job(
    kind: str,
    *,
    openai_json: dict[str, Any] | None = None,
    stability_service: str | None = None,
    or_json: dict[str, Any] | None = None,
    slug: str,
    ext: str,
) -> str:
    if kind == "openai" and openai_json:
        m = str(openai_json.get("model") or "openai")
        return f"{_fs_slug('openai', 12)}_{_fs_slug(m, 32)}_{slug}{ext}"
    if kind == "stability" and stability_service:
        return f"{_fs_slug('stability', 14)}_{_fs_slug(stability_service, 24)}_{slug}{ext}"
    if kind == "openrouter" and or_json:
        m = str(or_json.get("model") or "or")
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", m)[:80]
        return f"{_fs_slug('openrouter', 14)}_{safe}_{slug}{ext}"
    return f"{_fs_slug(kind, 20)}_{slug}{ext}"


@app.post("/api/run", response_model=BenchmarkRunResponse)
async def api_run(
    body: BenchmarkExecuteRequest,
    x_benchmark_key: str | None = Header(default=None, alias="X-Benchmark-Key"),
) -> BenchmarkRunResponse:
    _check_benchmark_key(x_benchmark_key)
    _validate_execute(body)

    s = get_settings()
    oa_key = (s.openai_api_key or "").strip()
    if body.openai_jsons and not oa_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Brak OPENAI_API_KEY")
    st_key = (s.stability_api_key or "").strip()
    if body.stability_jobs and not st_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Brak STABILITY_API_KEY")
    or_key = (s.openrouter_api_key or "").strip()
    if body.openrouter_image_jsons and not or_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Brak OPENROUTER_API_KEY")

    trace: list[dict[str, Any]] = [
        {
            "step": 1,
            "description": "Wykonanie — zatwierdzone payloady",
            "openai_jobs": len(body.openai_jsons),
            "stability_jobs": len(body.stability_jobs),
            "openrouter_image_jobs": len(body.openrouter_image_jsons),
            "t_start": time.monotonic(),
        },
    ]

    def _prompt_for_slug() -> str:
        if body.openai_jsons:
            return str(body.openai_jsons[0].get("prompt") or "")
        if body.stability_jobs:
            return str(body.stability_jobs[0].stability_form.get("prompt") or "")
        if body.openrouter_image_jsons:
            msgs = body.openrouter_image_jsons[0].get("messages")
            if isinstance(msgs, list) and msgs:
                c = msgs[0].get("content") if isinstance(msgs[0], dict) else None
                if isinstance(c, str):
                    return c
                if isinstance(c, list):
                    for part in c:
                        if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
                            return str(part["text"])
        return "image"

    slug = _slug_from_prompt(_prompt_for_slug())

    max_b64 = 10 * 1024 * 1024

    async def job_openai(oj: dict[str, Any]) -> tuple[str, dict[str, Any], bytes | None, list[dict[str, Any]], str | None, str, str]:
        mime = "image/png"
        ext = ".png"
        raw, tr, err = await openai_images_generate_raw(
            api_key=oa_key,
            base_url=s.openai_api_base_url,
            body=oj,
            timeout=body.openai_timeout_seconds,
        )
        fname = _filename_for_job("openai", openai_json=oj, slug=slug, ext=ext)
        return "openai", {"oj": oj}, raw, tr, err, mime, fname

    async def job_stability(job: StabilityJobItem) -> tuple[str, dict[str, Any], bytes | None, list[dict[str, Any]], str | None, str, str]:
        sf = job.stability_form
        fmt = str(sf.get("output_format") or "png").lower()
        mime = _mime_from_format(fmt)
        ext = ".jpg" if fmt in ("jpeg", "jpg") else f".{fmt}" if fmt in ("png", "webp") else ".png"
        raw, tr, err = await stability_generate_raw(
            api_key=st_key,
            base_url=s.stability_api_base_url,
            service=job.service,
            form_fields=job.stability_form,
            timeout=body.stability_timeout_seconds,
        )
        fname = _filename_for_job("stability", stability_service=job.service, slug=slug, ext=ext)
        return "stability", {"job": job}, raw, tr, err, mime, fname

    async def job_or(oj: dict[str, Any]) -> tuple[str, dict[str, Any], bytes | None, list[dict[str, Any]], str | None, str, str]:
        raw, tr, err = await openrouter_image_raw(
            api_key=or_key,
            base_url=s.openrouter_base_url,
            http_referer=(s.openrouter_http_referer or "").strip() or None,
            body=oj,
            timeout=body.openrouter_timeout_seconds,
        )
        fname = _filename_for_job("openrouter", or_json=oj, slug=slug, ext=".png")
        return "openrouter", {"oj": oj}, raw, tr, err, "image/png", fname

    coros: list[Any] = []
    for oj in body.openai_jsons:
        coros.append(job_openai(oj))
    for sj in body.stability_jobs:
        coros.append(job_stability(sj))
    for oj in body.openrouter_image_jsons:
        coros.append(job_or(oj))

    results = await asyncio.gather(*coros, return_exceptions=True)
    artifacts: list[ProviderArtifact] = []

    for item in results:
        if isinstance(item, Exception):
            trace.append({"provider": "?", "error": repr(item)})
            continue
        name, meta, raw, tr, err, mime, fname = item
        trace.extend([{**row, "parallel_job": name} if isinstance(row, dict) else row for row in tr])

        prov_label = name
        if name == "openai" and meta.get("oj"):
            prov_label = f"openai:{meta['oj'].get('model')}"
        elif name == "stability" and meta.get("job"):
            prov_label = f"stability:{meta['job'].service}"
        elif name == "openrouter" and meta.get("oj"):
            prov_label = f"openrouter:{meta['oj'].get('model')}"

        if err:
            artifacts.append(
                ProviderArtifact(
                    provider=prov_label,
                    ok=False,
                    filename=fname,
                    mime_type=mime,
                    error=err,
                ),
            )
            continue
        if raw and len(raw) > max_b64:
            artifacts.append(
                ProviderArtifact(
                    provider=prov_label,
                    ok=False,
                    filename=fname,
                    mime_type=mime,
                    error=f"Plik {len(raw)} B > limit {max_b64} B",
                    size_bytes=len(raw),
                ),
            )
            continue
        if raw:
            artifacts.append(
                ProviderArtifact(
                    provider=prov_label,
                    ok=True,
                    filename=fname,
                    mime_type=mime,
                    base64_image=_b64(raw),
                    size_bytes=len(raw),
                ),
            )
            continue
        artifacts.append(
            ProviderArtifact(
                provider=prov_label,
                ok=False,
                filename=fname,
                mime_type=mime,
                error="brak danych",
            ),
        )

    trace.append({"step": 2, "t_end": time.monotonic(), "artifacts_ok": sum(1 for a in artifacts if a.ok)})
    return BenchmarkRunResponse(trace=trace, artifacts=artifacts)


if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
