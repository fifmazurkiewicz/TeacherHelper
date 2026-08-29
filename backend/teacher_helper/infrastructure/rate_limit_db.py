"""Rejestr zdarzeń rate limit w PostgreSQL."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, delete, func, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from teacher_helper.infrastructure.db.base import Base


class RateLimitEventORM(Base):
    __tablename__ = "rate_limit_events"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


async def count_recent_events(session: AsyncSession, user_id: UUID, *, window_sec: int) -> int:
    since = datetime.now(timezone.utc) - timedelta(seconds=window_sec)
    stmt = select(func.count()).select_from(RateLimitEventORM).where(
        RateLimitEventORM.user_id == user_id,
        RateLimitEventORM.created_at >= since,
    )
    return int(await session.scalar(stmt) or 0)


async def record_event(session: AsyncSession, user_id: UUID) -> None:
    session.add(RateLimitEventORM(id=uuid.uuid4(), user_id=user_id))
    await session.flush()


async def prune_old_events(session: AsyncSession, *, older_than_sec: int = 7200) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_sec)
    await session.execute(delete(RateLimitEventORM).where(RateLimitEventORM.created_at < cutoff))
