from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, HTTPException, Response, status
from sqlalchemy import select

from teacher_helper.adapters.http.deps import CurrentUser, DbSession
from teacher_helper.adapters.http.schemas import (
    ConversationCreate,
    ConversationPatch,
    ConversationResponse,
    MessageResponse,
)
from teacher_helper.infrastructure.db.models import ConversationORM, MessageORM, ProjectORM

router = APIRouter(prefix="/v1/conversations", tags=["conversations"])


def _conv_out(c: ConversationORM) -> ConversationResponse:
    return ConversationResponse(
        id=c.id,
        title=c.title.strip() or "Nowa rozmowa",
        project_id=c.project_id,
        created_at=c.created_at,
        updated_at=c.updated_at,
    )


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(session: DbSession, user: CurrentUser) -> list[ConversationResponse]:
    stmt = (
        select(ConversationORM)
        .where(ConversationORM.user_id == user.id)
        .order_by(ConversationORM.updated_at.desc())
    )
    rows = (await session.scalars(stmt)).all()
    return [_conv_out(c) for c in rows]


@router.post("", response_model=ConversationResponse)
async def create_conversation(
    session: DbSession,
    user: CurrentUser,
    body: ConversationCreate | None = Body(None),
) -> ConversationResponse:
    payload = body if body is not None else ConversationCreate()
    title = (payload.title.strip() if payload.title else "") or ""
    c = ConversationORM(id=uuid4(), user_id=user.id, title=title)
    session.add(c)
    await session.commit()
    await session.refresh(c)
    return _conv_out(c)


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    session: DbSession, user: CurrentUser, conversation_id: UUID,
) -> list[MessageORM]:
    c = await session.get(ConversationORM, conversation_id)
    if not c or c.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rozmowa nie znaleziona")
    stmt = (
        select(MessageORM)
        .where(MessageORM.conversation_id == conversation_id)
        .order_by(MessageORM.created_at.asc())
    )
    return list((await session.scalars(stmt)).all())


@router.post("/{conversation_id}/ensure-folder", response_model=ConversationResponse)
async def ensure_conversation_folder(
    session: DbSession, user: CurrentUser, conversation_id: UUID,
) -> ConversationResponse:
    """Tworzy (jeśli trzeba) katalog projektu powiązany z rozmową — pliki z Asystenta trafiają do „Moje materiały”."""
    c = await session.get(ConversationORM, conversation_id)
    if not c or c.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rozmowa nie znaleziona")
    if c.project_id is not None:
        existing = await session.get(ProjectORM, c.project_id)
        if existing is not None and existing.user_id == user.id:
            return _conv_out(c)
        c.project_id = None
    base = (c.title or "").strip() or "Nowa rozmowa"
    name = base[:500]
    p = ProjectORM(
        id=uuid4(),
        user_id=user.id,
        name=name,
        description="Katalog powiązany z tą rozmową w Asystencie — pliki dodane z czatu trafiają tutaj.",
    )
    session.add(p)
    await session.flush()
    c.project_id = p.id
    c.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(c)
    return _conv_out(c)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def patch_conversation(
    session: DbSession, user: CurrentUser, conversation_id: UUID, body: ConversationPatch,
) -> ConversationResponse:
    c = await session.get(ConversationORM, conversation_id)
    if not c or c.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rozmowa nie znaleziona")
    updates = body.model_dump(exclude_unset=True)
    if "title" in updates and updates["title"] is not None:
        t = str(updates["title"]).strip()
        if len(t) < 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Tytuł nie może być pusty")
        c.title = t
    if "project_id" in updates:
        pid = updates["project_id"]
        if pid is not None:
            p = await session.get(ProjectORM, pid)
            if not p or p.user_id != user.id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Projekt nie znaleziony")
        c.project_id = pid
    c.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(c)
    return _conv_out(c)


@router.delete("/{conversation_id}", response_model=None)
async def delete_conversation(
    session: DbSession, user: CurrentUser, conversation_id: UUID,
) -> Response:
    c = await session.get(ConversationORM, conversation_id)
    if not c or c.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rozmowa nie znaleziona")
    await session.delete(c)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
