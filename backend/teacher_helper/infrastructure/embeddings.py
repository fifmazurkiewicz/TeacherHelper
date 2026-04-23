from __future__ import annotations

import asyncio
import hashlib
import logging
import math
from typing import Literal, Sequence

import httpx

from teacher_helper.config import Settings, get_settings
from teacher_helper.infrastructure.db.llm_usage import (
    record_langfuse_model_call_sync,
    usage_from_embeddings_response,
)

logger = logging.getLogger(__name__)

_OPENAI_BATCH_SIZE = 100
# W EMBEDDINGS_BACKEND=auto po pierwszym 401 z OpenAI nie ponawiamy wywołań do OpenAI w tym procesie.
_skip_openai_embeddings: bool = False


def _resolve_embeddings_route(s: Settings) -> Literal["openai", "openrouter", "stub"]:
    b = s.embeddings_backend
    if b == "openrouter":
        return "openrouter" if s.openrouter_api_key else "stub"
    if b == "openai":
        return "openai" if s.openai_api_key else "stub"
    if s.openai_api_key:
        return "openai"
    if s.openrouter_api_key:
        return "openrouter"
    return "stub"


def _openrouter_headers(s: Settings) -> dict[str, str]:
    h: dict[str, str] = {
        "Authorization": f"Bearer {s.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    if s.openrouter_http_referer:
        h["HTTP-Referer"] = s.openrouter_http_referer.strip()
    if s.app_name:
        h["X-Title"] = s.app_name
    return h


async def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Embeddingi: OpenAI, OpenRouter (/v1/embeddings) lub deterministyczny stub."""
    global _skip_openai_embeddings
    s = get_settings()
    route = _resolve_embeddings_route(s)
    if s.embeddings_backend == "auto" and _skip_openai_embeddings:
        route = "openrouter" if s.openrouter_api_key else "stub"
    if route == "stub":
        return [_stub_embedding(t, s.embedding_dim) for t in texts]
    if route == "openrouter":
        return await _openrouter_embed_batched(
            texts,
            s,
            model=s.openrouter_embedding_model,
            dimensions=s.embedding_dim,
        )
    try:
        return await _openai_embed_batched(
            texts,
            api_key=s.openai_api_key,  # type: ignore[arg-type]
            model=s.openai_embedding_model,
            dimensions=s.embedding_dim,
        )
    except RuntimeError as e:
        err = str(e)
        if (
            s.embeddings_backend == "auto"
            and s.openrouter_api_key
            and ("401" in err or "HTTP 401" in err or "invalid_api_key" in err)
        ):
            logger.warning(
                "OpenAI embeddings odrzucone (401); używam OpenRouter. "
                "Ustaw EMBEDDINGS_BACKEND=openrouter albo popraw OPENAI_API_KEY; "
                "do restartu procesu kolejne zapytania w auto pominą OpenAI."
            )
            _skip_openai_embeddings = True
            return await _openrouter_embed_batched(
                texts,
                s,
                model=s.openrouter_embedding_model,
                dimensions=s.embedding_dim,
            )
        raise


async def embed_text(text: str) -> list[float]:
    result = await embed_texts([text])
    return result[0]


async def _openai_embed_batched(
    texts: Sequence[str],
    api_key: str,
    model: str,
    dimensions: int,
) -> list[list[float]]:
    all_embeddings: list[list[float]] = [[] for _ in texts]
    for start in range(0, len(texts), _OPENAI_BATCH_SIZE):
        batch = texts[start : start + _OPENAI_BATCH_SIZE]
        batch_result = await _openai_embed(batch, api_key, model, dimensions)
        for i, emb in enumerate(batch_result):
            all_embeddings[start + i] = emb
    return all_embeddings


async def _openai_embed(
    texts: Sequence[str],
    api_key: str,
    model: str,
    dimensions: int,
) -> list[list[float]]:
    payload: dict = {
        "model": model,
        "input": list(texts),
    }
    if "3" in model:
        payload["dimensions"] = dimensions

    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            "https://api.openai.com/v1/embeddings",
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
    if r.is_error:
        detail = r.text[:500] if r.text else r.reason_phrase
        raise RuntimeError(f"OpenAI Embeddings HTTP {r.status_code}: {detail}")

    payload = r.json()
    vecs = _embeddings_response_vectors(payload)
    usage = usage_from_embeddings_response(payload) if isinstance(payload, dict) else None
    await asyncio.to_thread(
        record_langfuse_model_call_sync,
        observation_name="openai:embeddings",
        model=model,
        provider="openai",
        input_data={"batch_size": len(texts), "sample": (texts[0][:500] if texts else "")},
        output_text=f"vectors={len(vecs)} dim={len(vecs[0]) if vecs else 0}",
        user_id=None,
        metadata={"call_kind": "embeddings"},
        usage=usage,
    )
    return vecs


async def _openrouter_embed_batched(
    texts: Sequence[str],
    s: Settings,
    model: str,
    dimensions: int,
) -> list[list[float]]:
    if not s.openrouter_api_key:
        raise RuntimeError("OpenRouter embeddings wymagają OPENROUTER_API_KEY")
    all_embeddings: list[list[float]] = [[] for _ in texts]
    base = s.openrouter_base_url.rstrip("/")
    headers = _openrouter_headers(s)
    for start in range(0, len(texts), _OPENAI_BATCH_SIZE):
        batch = texts[start : start + _OPENAI_BATCH_SIZE]
        payload: dict = {
            "model": model,
            "input": list(batch),
            "encoding_format": "float",
        }
        if "3" in model:
            payload["dimensions"] = dimensions
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{base}/embeddings", json=payload, headers=headers)
        if r.is_error:
            detail = r.text[:500] if r.text else r.reason_phrase
            raise RuntimeError(f"OpenRouter Embeddings HTTP {r.status_code}: {detail}")
        payload = r.json()
        batch_vectors = _embeddings_response_vectors(payload)
        usage = usage_from_embeddings_response(payload) if isinstance(payload, dict) else None
        await asyncio.to_thread(
            record_langfuse_model_call_sync,
            observation_name="openrouter:embeddings",
            model=model,
            provider="openrouter",
            input_data={"batch_size": len(batch), "sample": (batch[0][:500] if batch else "")},
            output_text=f"vectors={len(batch_vectors)} dim={len(batch_vectors[0]) if batch_vectors else 0}",
            user_id=None,
            metadata={"call_kind": "embeddings"},
            usage=usage,
        )
        for i, emb in enumerate(batch_vectors):
            all_embeddings[start + i] = emb
    return all_embeddings


def _embeddings_response_vectors(data: dict) -> list[list[float]]:
    items = sorted(data["data"], key=lambda x: x["index"])
    return [item["embedding"] for item in items]


def _stub_embedding(text: str, dim: int) -> list[float]:
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    out: list[float] = []
    for i in range(dim):
        b0 = seed[i % 32]
        b1 = seed[(i + 7) % 32]
        b2 = seed[(i + 13) % 32]
        b3 = seed[(i + 19) % 32]
        val = ((b0 << 24) | (b1 << 16) | (b2 << 8) | b3) / (2**31) - 1.0
        out.append(max(-1.0, min(1.0, val)))
    norm = math.sqrt(sum(x * x for x in out)) or 1.0
    return [x / norm for x in out]
