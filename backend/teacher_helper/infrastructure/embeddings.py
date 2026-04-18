from __future__ import annotations

import hashlib
import math
from typing import Sequence

import httpx

from teacher_helper.config import get_settings

_OPENAI_BATCH_SIZE = 100


async def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Wygeneruj embeddingi dla listy tekstów (OpenAI → stub fallback)."""
    s = get_settings()
    if s.openai_api_key:
        return await _openai_embed_batched(
            texts,
            api_key=s.openai_api_key,
            model=s.openai_embedding_model,
            dimensions=s.embedding_dim,
        )
    return [_stub_embedding(t, s.embedding_dim) for t in texts]


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

    data = r.json()
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
