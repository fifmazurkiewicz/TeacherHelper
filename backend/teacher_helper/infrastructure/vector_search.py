"""Wyszukiwanie semantyczne chunków w PostgreSQL (pgvector)."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_helper.config import get_settings


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"


def rag_score_passes(score: float, min_score: float | None) -> bool:
    if min_score is None:
        return True
    return float(score) >= float(min_score)


def apply_rag_sql_filters(
    *,
    project_id: UUID | None = None,
    topic_id: UUID | None = None,
    min_score: float | None = None,
    library_only: bool = False,
) -> tuple[str, dict]:
    """WHERE fragments applied inside ``search_vector_chunks`` (not post-fetch)."""
    clauses: list[str] = []
    params: dict = {}
    if topic_id is not None:
        clauses.append("AND fa.topic_id = CAST(:topic_id AS uuid)")
        params["topic_id"] = str(topic_id)
    elif library_only:
        clauses.append("AND fa.topic_id IS NULL")
    if project_id is not None:
        clauses.append("AND fa.project_id = CAST(:project_id AS uuid)")
        params["project_id"] = str(project_id)
    if min_score is not None:
        clauses.append("AND (1 - (fc.embedding <=> CAST(:q AS vector))) >= :min_score")
        params["min_score"] = float(min_score)
    return "\n              ".join(clauses), params


async def search_vector_chunks(
    session: AsyncSession,
    user_id: UUID,
    query_vector: list[float],
    top_k: int = 8,
    *,
    topic_id: UUID | None = None,
    project_id: UUID | None = None,
    min_score: float | None = None,
    library_only: bool = False,
) -> list[dict]:
    """Cosine distance na ``file_chunks.embedding`` z joinem do ``file_assets``."""
    dim = get_settings().embedding_dim
    if len(query_vector) != dim:
        raise ValueError(f"Wymiar wektora {len(query_vector)} != {dim}")

    vec = _vector_literal(query_vector)
    extra_sql, extra_params = apply_rag_sql_filters(
        project_id=project_id,
        topic_id=topic_id,
        min_score=min_score,
        library_only=library_only and topic_id is None,
    )
    sql = text(
        f"""
            SELECT fc.id::text AS id,
                   1 - (fc.embedding <=> CAST(:q AS vector)) AS score,
                   fc.file_asset_id::text AS file_asset_id,
                   fc.chunk_index AS chunk_index,
                   fc.text AS text
            FROM file_chunks fc
            JOIN file_assets fa ON fa.id = fc.file_asset_id
            WHERE fa.user_id = CAST(:user_id AS uuid)
              {extra_sql}
            ORDER BY fc.embedding <=> CAST(:q AS vector)
            LIMIT :limit
            """
    )
    params = {"q": vec, "user_id": str(user_id), "limit": top_k, **extra_params}

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
        if rag_score_passes(float(row["score"] or 0.0), min_score)
    ]
