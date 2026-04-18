"""Operacje na projektach wywoływane z orchestratora (tool calling)."""
from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from teacher_helper.infrastructure.db.models import ProjectORM


async def create_teacher_project_in_db(
    session: AsyncSession,
    user_id: UUID,
    name: str,
    description: str | None = None,
) -> UUID:
    """Tworzy rekord projektu i zwraca jego id (po flush)."""
    pname = name.strip()
    if not pname:
        raise ValueError("Brak nazwy projektu")
    desc = description.strip() if description else None
    proj = ProjectORM(
        id=uuid.uuid4(),
        user_id=user_id,
        name=pname[:500],
        description=desc,
    )
    session.add(proj)
    await session.flush()
    return proj.id
