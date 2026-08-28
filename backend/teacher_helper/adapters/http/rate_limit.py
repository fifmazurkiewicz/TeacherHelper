from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_helper.config import get_settings
from teacher_helper.infrastructure.db.models import UserORM
from teacher_helper.infrastructure.rate_limit_db import count_recent_events, prune_old_events, record_event

_window_sec = 60


async def check_rate_limit(session: AsyncSession, user: UserORM) -> None:
    limit = user.rate_limit_rpm if user.rate_limit_rpm is not None else get_settings().default_rate_limit_rpm
    current = await count_recent_events(session, user.id, window_sec=_window_sec)
    if current >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Zbyt wiele żądań (limit: {limit}/min) — spróbuj za chwilę.",
        )
    await record_event(session, user.id)
    if current % 50 == 0:
        await prune_old_events(session)
