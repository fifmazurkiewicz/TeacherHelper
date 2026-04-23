"""Klient Qdrant — jedna kolekcja, izolacja: payload user_id + topic_id."""
from __future__ import annotations

import logging
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from teacher_helper.config import get_settings

logger = logging.getLogger(__name__)

_client: QdrantClient | None = None


def get_qdrant() -> QdrantClient:
    global _client
    if _client is None:
        s = get_settings()
        _client = QdrantClient(
            url=s.qdrant_url,
            api_key=s.qdrant_api_key,
            timeout=30.0,
            check_compatibility=False,
        )
    return _client


def _ensure_payload_indexes(client: QdrantClient, collection_name: str) -> None:
    """Indeksy keyword na polach używanych w filtrach (Qdrant wymaga ich przy delete/query)."""
    for field_name in ("user_id", "topic_id", "file_asset_id"):
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema="keyword",
            )
            logger.debug("Indeks payload Qdrant: %s.%s", collection_name, field_name)
        except Exception as exc:
            err = str(exc).lower()
            if "already exists" in err or "duplicate" in err or "409" in err:
                continue
            logger.warning("Qdrant create_payload_index %s.%s: %s", collection_name, field_name, exc)


def ensure_collection() -> None:
    """Utwórz kolekcję jeśli nie istnieje; upewnij się co do indeksów payload."""
    s = get_settings()
    client = get_qdrant()
    collections = [c.name for c in client.get_collections().collections]
    if s.qdrant_collection not in collections:
        client.create_collection(
            collection_name=s.qdrant_collection,
            vectors_config=VectorParams(
                size=s.embedding_dim,
                distance=Distance.COSINE,
            ),
        )
        logger.debug("Utworzono kolekcję Qdrant: %s (dim=%d)", s.qdrant_collection, s.embedding_dim)
    _ensure_payload_indexes(client, s.qdrant_collection)


def _topic_payload_value(topic_id: UUID | None) -> str:
    """Pusty string = biblioteka / asystent; UUID jako str = jeden temat Omówienia."""
    return str(topic_id) if topic_id is not None else ""


def upsert_chunks(
    file_asset_id: UUID,
    user_id: UUID,
    chunk_ids: list[UUID],
    texts: list[str],
    embeddings: list[list[float]],
    topic_id: UUID | None = None,
) -> None:
    s = get_settings()
    client = get_qdrant()
    _ensure_payload_indexes(client, s.qdrant_collection)
    topic_key = _topic_payload_value(topic_id)
    points = [
        PointStruct(
            id=str(cid),
            vector=emb,
            payload={
                "file_asset_id": str(file_asset_id),
                "user_id": str(user_id),
                "topic_id": topic_key,
                "chunk_index": idx,
                "text": text,
            },
        )
        for idx, (cid, text, emb) in enumerate(zip(chunk_ids, texts, embeddings, strict=True))
    ]
    client.upsert(collection_name=s.qdrant_collection, points=points)


def delete_file_vectors(file_asset_id: UUID) -> None:
    """Usuwa punkty po ``file_asset_id``. Przy niedostępnym Qdrancie (np. dev bez Dockera) tylko loguje — plik i tak można skasować w PG/storage."""
    s = get_settings()
    try:
        client = get_qdrant()
        _ensure_payload_indexes(client, s.qdrant_collection)
        client.delete(
            collection_name=s.qdrant_collection,
            points_selector=Filter(
                must=[FieldCondition(key="file_asset_id", match=MatchValue(value=str(file_asset_id)))]
            ),
        )
    except Exception as exc:
        logger.warning(
            "Qdrant niedostępny — pomijam usuwanie wektorów dla pliku %s: %s",
            file_asset_id,
            exc,
        )


def search_vectors(
    query_vector: list[float],
    user_id: UUID,
    top_k: int = 8,
    *,
    topic_id: UUID | None = None,
) -> list[dict]:
    """Wyszukiwanie wektorowe: zawsze filtr user_id; opcjonalnie dokładny topic_id w payload."""
    s = get_settings()
    client = get_qdrant()
    _ensure_payload_indexes(client, s.qdrant_collection)

    must_filters = [
        FieldCondition(key="user_id", match=MatchValue(value=str(user_id))),
    ]
    if topic_id is not None:
        must_filters.append(
            FieldCondition(key="topic_id", match=MatchValue(value=str(topic_id))),
        )

    # qdrant-client >= ~1.17: ``search`` usunięte na rzecz Query API
    response = client.query_points(
        collection_name=s.qdrant_collection,
        query=query_vector,
        query_filter=Filter(must=must_filters),
        limit=top_k,
        with_payload=True,
    )
    results = response.points

    return [
        {
            "id": str(hit.id),
            "score": hit.score,
            "file_asset_id": hit.payload.get("file_asset_id") if hit.payload else None,
            "chunk_index": hit.payload.get("chunk_index") if hit.payload else None,
            "text": hit.payload.get("text", "") if hit.payload else "",
        }
        for hit in results
    ]
