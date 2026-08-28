"""Wyszukiwanie semantyczne chunków w PostgreSQL (pgvector)."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_helper.config import get_settings


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"


async def search_vector_chunks(
    session: AsyncSession,
    user_id: UUID,
    query_vector: list[float],
    top_k: int = 8,
    *,
    topic_id: UUID | None = None,
) -> list[dict]:
    """Cosine distance na ``file_chunks.embedding`` z joinem do ``file_assets``."""
    dim = get_settings().embedding_dim
    if len(query_vector) != dim:
        raise ValueError(f"Wymiar wektora {len(query_vector)} != {dim}")

    vec = _vector_literal(query_vector)
    if topic_id is not None:
        sql = text(
            """
            SELECT fc.id::text AS id,
                   1 - (fc.embedding <=> CAST(:q AS vector)) AS score,
                   fc.file_asset_id::text AS file_asset_id,
                   fc.chunk_index AS chunk_index,
                   fc.text AS text
            FROM file_chunks fc
            JOIN file_assets fa ON fa.id = fc.file_asset_id
            WHERE fa.user_id = CAST(:user_id AS uuid)
              AND fa.topic_id = CAST(:topic_id AS uuid)
            ORDER BY fc.embedding <=> CAST(:q AS vector)
            LIMIT :limit
            """
        )
        params = {"q": vec, "user_id": str(user_id), "topic_id": str(topic_id), "limit": top_k}
    else:
        sql = text(
            """
            SELECT fc.id::text AS id,
                   1 - (fc.embedding <=> CAST(:q AS vector)) AS score,
                   fc.file_asset_id::text AS file_asset_id,
                   fc.chunk_index AS chunk_index,
                   fc.text AS text
            FROM file_chunks fc
            JOIN file_assets fa ON fa.id = fc.file_asset_id
            WHERE fa.user_id = CAST(:user_id AS uuid)
            ORDER BY fc.embedding <=> CAST(:q AS vector)
            LIMIT :limit
            """
        )
        params = {"q": vec, "user_id": str(user_id), "limit": top_k}

    rows = (await session.execute(sql, params)).mappings().all()
    return [
        {
            "id": row["id"],
            "score": float(row["score"] or 0.0),
            "file_asset_id": row["file_asset_id"],
            "chunk_index": row["chunk_index"],
            "text": row["text"] or "",
        }
        for row in rows
    ]
