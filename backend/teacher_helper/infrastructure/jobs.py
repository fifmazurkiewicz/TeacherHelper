"""Operacje na zadaniach generacji (czat w tle)."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, func, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from teacher_helper.infrastructure.db.base import Base
from teacher_helper.infrastructure.db.models import ConversationORM

STALE_RUNNING_JOB_MESSAGE = (
    "Zadanie utknęło (przekroczono limit czasu 15 minut). Spróbuj ponownie."
)


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"


class GenerationJobORM(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, default="chat")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=JobStatus.pending.value, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


async def create_job(
    session: AsyncSession,
    *,
    user_id: UUID,
    kind: str,
    payload: dict[str, Any],
    conversation_id: UUID | None = None,
) -> GenerationJobORM:
    job = GenerationJobORM(
        id=uuid.uuid4(),
        user_id=user_id,
        kind=kind,
        status=JobStatus.pending.value,
        payload=payload,
        conversation_id=conversation_id,
    )
    session.add(job)
    await session.flush()
    return job


async def claim_job_running(session: AsyncSession, job_id: UUID) -> bool:
    """CAS: pending → running. Returns False if the job is already running or finished."""
    result = await session.execute(
        update(GenerationJobORM)
        .where(
            GenerationJobORM.id == job_id,
            GenerationJobORM.status == JobStatus.pending.value,
        )
        .values(status=JobStatus.running.value, updated_at=datetime.now(timezone.utc))
        .returning(GenerationJobORM.id)
    )
    claimed_id = result.scalar_one_or_none()
    if claimed_id is not None:
        return True
    return bool(getattr(result, "rowcount", 0))


async def mark_job_running(session: AsyncSession, job_id: UUID) -> bool:
    """CAS wrapper — only pending jobs become running."""
    return await claim_job_running(session, job_id)


def lock_conversation_for_job_stmt(conversation_id: UUID):
    """SELECT conversation … FOR UPDATE — serializes check+create of an active chat job."""
    return (
        select(ConversationORM)
        .where(ConversationORM.id == conversation_id)
        .with_for_update()
    )


async def lock_conversation_for_job(
    session: AsyncSession,
    conversation_id: UUID,
) -> ConversationORM | None:
    return await session.scalar(lock_conversation_for_job_stmt(conversation_id))


async def conversation_has_active_chat_job(
    session: AsyncSession,
    conversation_id: UUID,
) -> GenerationJobORM | None:
    stmt = (
        select(GenerationJobORM)
        .where(
            GenerationJobORM.conversation_id == conversation_id,
            GenerationJobORM.kind == "chat",
            GenerationJobORM.status.in_((JobStatus.pending.value, JobStatus.running.value)),
        )
        .order_by(GenerationJobORM.created_at.desc())
        .limit(1)
    )
    return await session.scalar(stmt)


async def reap_stale_running_jobs(
    session: AsyncSession,
    max_age_minutes: int = 15,
    pending_max_age_minutes: int = 5,
) -> int:
    now = datetime.now(timezone.utc)
    running_cutoff = now - timedelta(minutes=max_age_minutes)
    pending_cutoff = now - timedelta(minutes=pending_max_age_minutes)
    running = await session.execute(
        update(GenerationJobORM)
        .where(
            GenerationJobORM.status == JobStatus.running.value,
            GenerationJobORM.updated_at < running_cutoff,
        )
        .values(
            status=JobStatus.error.value,
            error=STALE_RUNNING_JOB_MESSAGE,
            updated_at=now,
        )
    )
    pending = await session.execute(
        update(GenerationJobORM)
        .where(
            GenerationJobORM.status == JobStatus.pending.value,
            GenerationJobORM.updated_at < pending_cutoff,
        )
        .values(
            status=JobStatus.error.value,
            error=STALE_RUNNING_JOB_MESSAGE,
            updated_at=now,
        )
    )
    return int((running.rowcount or 0) + (pending.rowcount or 0))


async def mark_job_done(session: AsyncSession, job_id: UUID, result: dict[str, Any]) -> bool:
    res = await session.execute(
        update(GenerationJobORM)
        .where(
            GenerationJobORM.id == job_id,
            GenerationJobORM.status == JobStatus.running.value,
        )
        .values(
            status=JobStatus.done.value,
            result=result,
            error=None,
            updated_at=datetime.now(timezone.utc),
        )
    )
    return int(res.rowcount or 0) > 0


async def mark_job_error(session: AsyncSession, job_id: UUID, message: str) -> bool:
    res = await session.execute(
        update(GenerationJobORM)
        .where(
            GenerationJobORM.id == job_id,
            GenerationJobORM.status.in_((JobStatus.pending.value, JobStatus.running.value)),
        )
        .values(
            status=JobStatus.error.value,
            error=message[:4000],
            updated_at=datetime.now(timezone.utc),
        )
    )
    return int(res.rowcount or 0) > 0


async def get_job_for_user(session: AsyncSession, job_id: UUID, user_id: UUID) -> GenerationJobORM | None:
    job = await session.get(GenerationJobORM, job_id)
    if job is None or job.user_id != user_id:
        return None
    return job


async def get_job(session: AsyncSession, job_id: UUID) -> GenerationJobORM | None:
    return await session.get(GenerationJobORM, job_id)
