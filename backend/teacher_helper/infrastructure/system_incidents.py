from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_helper.infrastructure.db.models import SystemIncidentORM


async def record_system_incident(
    session: AsyncSession,
    *,
    event_type: str,
    severity: str,
    title: str,
    detail: dict | None = None,
    user_id: UUID | None = None,
) -> SystemIncidentORM:
    row = SystemIncidentORM(
        id=uuid4(),
        event_type=event_type[:120],
        severity=severity[:32],
        title=title[:500],
        detail_json=json.dumps(detail, ensure_ascii=False) if detail else None,
        user_id=user_id,
    )
    session.add(row)
    await session.flush()
    return row


async def count_recent_incidents(
    session: AsyncSession,
    *,
    event_type: str,
    since: datetime,
) -> int:
    n = await session.scalar(
        select(func.count())
        .select_from(SystemIncidentORM)
        .where(SystemIncidentORM.event_type == event_type, SystemIncidentORM.created_at >= since)
    )
    return int(n or 0)


async def list_recent_incidents(session: AsyncSession, *, limit: int = 50) -> list[SystemIncidentORM]:
    stmt = (
        select(SystemIncidentORM).order_by(SystemIncidentORM.created_at.desc()).limit(min(limit, 200))
    )
    return list((await session.scalars(stmt)).all())
