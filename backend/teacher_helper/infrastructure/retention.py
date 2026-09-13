from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_helper.config import get_settings
from teacher_helper.infrastructure.db.models import LlmUsageLogORM, SystemIncidentORM
from teacher_helper.infrastructure.jobs import GenerationJobORM, JobStatus


async def enforce_operational_retention(session: AsyncSession) -> dict[str, int]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    terminal_jobs = await session.execute(
        delete(GenerationJobORM).where(
            GenerationJobORM.status.in_((JobStatus.done.value, JobStatus.error.value)),
            GenerationJobORM.updated_at < now - timedelta(days=settings.generation_job_retention_days),
        )
    )
    usage = await session.execute(
        delete(LlmUsageLogORM).where(
            LlmUsageLogORM.created_at < now - timedelta(days=settings.llm_usage_retention_days)
        )
    )
    incidents = await session.execute(
        delete(SystemIncidentORM).where(
            SystemIncidentORM.created_at < now - timedelta(days=settings.system_incident_retention_days)
        )
    )
    return {
        "generation_jobs": int(terminal_jobs.rowcount or 0),
        "llm_usage": int(usage.rowcount or 0),
        "system_incidents": int(incidents.rowcount or 0),
    }
