"""Operacje na zadaniach generacji (czat w tle)."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, func, select, update
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from teacher_helper.infrastructure.db.base import Base


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


async def mark_job_running(session: AsyncSession, job_id: UUID) -> None:
    await session.execute(
        update(GenerationJobORM)
        .where(GenerationJobORM.id == job_id)
        .values(status=JobStatus.running.value, updated_at=datetime.now(timezone.utc))
    )


async def mark_job_done(session: AsyncSession, job_id: UUID, result: dict[str, Any]) -> None:
    await session.execute(
        update(GenerationJobORM)
        .where(GenerationJobORM.id == job_id)
        .values(
            status=JobStatus.done.value,
            result=result,
            error=None,
            updated_at=datetime.now(timezone.utc),
        )
    )


async def mark_job_error(session: AsyncSession, job_id: UUID, message: str) -> None:
    await session.execute(
        update(GenerationJobORM)
        .where(GenerationJobORM.id == job_id)
        .values(
            status=JobStatus.error.value,
            error=message[:4000],
            updated_at=datetime.now(timezone.utc),
        )
    )


async def get_job_for_user(session: AsyncSession, job_id: UUID, user_id: UUID) -> GenerationJobORM | None:
    job = await session.get(GenerationJobORM, job_id)
    if job is None or job.user_id != user_id:
        return None
    return job


async def get_job(session: AsyncSession, job_id: UUID) -> GenerationJobORM | None:
    return await session.get(GenerationJobORM, job_id)
