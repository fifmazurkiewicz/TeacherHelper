from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from teacher_helper.adapters.http.deps import ApprovedUser, DbSession
from teacher_helper.adapters.http.schemas import JobStatusResponse
from teacher_helper.infrastructure.jobs import JobStatus, get_job_for_user

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(session: DbSession, user: ApprovedUser, job_id: UUID) -> JobStatusResponse:
    job = await get_job_for_user(session, job_id, user.id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Zadanie nie znalezione")
    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        kind=job.kind,
        conversation_id=job.conversation_id,
        result=job.result if job.status == JobStatus.done.value else None,
        error=job.error if job.status == JobStatus.error.value else None,
    )
