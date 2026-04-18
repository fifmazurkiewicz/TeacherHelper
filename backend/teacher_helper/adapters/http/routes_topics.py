from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select

from teacher_helper.adapters.http.deps import CurrentUser, DbSession
from teacher_helper.adapters.http.rate_limit import check_rate_limit
from teacher_helper.adapters.http.schemas import TopicCreate, TopicResponse, TopicSearchHit
from teacher_helper.infrastructure.db.file_ops import semantic_search_chunks
from teacher_helper.infrastructure.db.models import FileAssetORM, TopicORM

router = APIRouter(prefix="/v1/topics", tags=["topics"])


@router.post("", response_model=TopicResponse)
async def create_topic(session: DbSession, user: CurrentUser, body: TopicCreate) -> TopicORM:
    check_rate_limit(user)
    row = TopicORM(
        id=uuid4(),
        user_id=user.id,
        name=body.name.strip(),
        description=body.description.strip() if body.description else None,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("", response_model=list[TopicResponse])
async def list_topics(session: DbSession, user: CurrentUser) -> list[TopicORM]:
    stmt = select(TopicORM).where(TopicORM.user_id == user.id).order_by(TopicORM.created_at.desc())
    return list((await session.scalars(stmt)).all())


@router.get("/{topic_id}", response_model=TopicResponse)
async def get_topic(session: DbSession, user: CurrentUser, topic_id: UUID) -> TopicORM:
    row = await session.get(TopicORM, topic_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Temat nie znaleziony")
    return row


@router.delete("/{topic_id}", response_model=None)
async def delete_topic(session: DbSession, user: CurrentUser, topic_id: UUID) -> Response:
    check_rate_limit(user)
    row = await session.get(TopicORM, topic_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Temat nie znaleziony")
    n_files = await session.scalar(
        select(func.count()).select_from(FileAssetORM).where(FileAssetORM.topic_id == topic_id)
    )
    if int(n_files or 0) > 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Temat ma przypisane pliki — usuń je lub przenieś (topic_id), potem spróbuj ponownie.",
        )
    await session.delete(row)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{topic_id}/search", response_model=list[TopicSearchHit])
async def search_topic_rag(
    session: DbSession,
    user: CurrentUser,
    topic_id: UUID,
    q: str = Query(..., min_length=1, max_length=2000, description="Zapytanie semantyczne w obrębie tematu"),
    top_k: int = Query(8, ge=1, le=32),
) -> list[TopicSearchHit]:
    """Prosty RAG: Qdrant z filtrem user_id + topic_id (bez mieszania między tematami)."""
    check_rate_limit(user)
    topic = await session.get(TopicORM, topic_id)
    if not topic or topic.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Temat nie znaleziony")
    hits = await semantic_search_chunks(
        session, user.id, q, top_k=top_k, project_id=None, topic_id=topic_id
    )
    return [
        TopicSearchHit(
            text=c.text,
            score=s,
            file_id=c.file_asset_id,
            chunk_index=c.chunk_index,
            file_name=c.file_asset.name if c.file_asset else "",
        )
        for c, s in hits
    ]
