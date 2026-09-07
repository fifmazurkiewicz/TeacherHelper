from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from teacher_helper.adapters.http.deps import ApprovedUser, DbSession
from teacher_helper.adapters.http.rate_limit import check_rate_limit
from teacher_helper.adapters.http.schemas import ChatAcceptedResponse, ChatRequest
from teacher_helper.config import get_settings
from teacher_helper.infrastructure.alert_webhook import send_alert_webhook
from teacher_helper.infrastructure.db.models import ConversationORM, MessageORM, ProjectORM
from teacher_helper.infrastructure.db.session import async_session_factory
from teacher_helper.infrastructure.jobs import (
    conversation_has_active_chat_job,
    create_job,
    lock_conversation_for_job,
    reap_stale_running_jobs,
)
from teacher_helper.infrastructure.system_incidents import record_system_incident
from teacher_helper.infrastructure.usage_limits import (
    effective_user_llm_monthly_cost_limit_usd,
    sum_llm_cost_usd_month,
    sum_llm_cost_usd_month_for_user,
)
from teacher_helper.use_cases.chat_job_runner import run_chat_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/chat", tags=["chat"])


@router.post("", response_model=ChatAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def chat(session: DbSession, user: ApprovedUser, body: ChatRequest) -> JSONResponse:
    await check_rate_limit(session, user)
    s = get_settings()
    cost_month = await sum_llm_cost_usd_month(session, include_dry_run=False)
    if s.llm_monthly_cost_hard_limit_usd is not None and cost_month >= s.llm_monthly_cost_hard_limit_usd:
        async with async_session_factory() as inc_sess:
            await record_system_incident(
                inc_sess,
                event_type="llm_hard_limit_blocked",
                severity="critical",
                title="Żądanie czatu zablokowane — miesięczny limit kosztu LLM",
                detail={"cost_month_usd": cost_month, "hard_limit_usd": s.llm_monthly_cost_hard_limit_usd},
                user_id=user.id,
            )
            await inc_sess.commit()
        await send_alert_webhook(
            {
                "event": "llm_hard_limit_blocked",
                "severity": "critical",
                "cost_month_usd": cost_month,
                "hard_limit_usd": s.llm_monthly_cost_hard_limit_usd,
                "user_id": str(user.id),
            }
        )
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Miesięczny limit kosztu LLM został wyczerpany. Skontaktuj się z administratorem lub spróbuj w kolejnym miesiącu (UTC).",
        )

    eff_user_monthly = effective_user_llm_monthly_cost_limit_usd(user, s)
    if eff_user_monthly is not None:
        user_cost_month = await sum_llm_cost_usd_month_for_user(session, user.id, include_dry_run=False)
        if user_cost_month >= eff_user_monthly:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Osiągnięto miesięczny limit kosztu LLM (${eff_user_monthly:.2f}, UTC) dla Twojego konta. "
                    "Skontaktuj się z administratorem lub spróbuj w kolejnym miesiącu."
                ),
            )

    if body.conversation_id is not None:
        conv = await lock_conversation_for_job(session, body.conversation_id)
        if not conv or conv.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rozmowa nie znaleziona")
    else:
        conv = ConversationORM(id=uuid4(), user_id=user.id, title="")
        session.add(conv)
        await session.flush()
        locked = await lock_conversation_for_job(session, conv.id)
        if locked is not None:
            conv = locked

    if body.project_id is not None:
        p = await session.get(ProjectORM, body.project_id)
        if not p or p.user_id != user.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Projekt nie znaleziony")
        conv.project_id = body.project_id

    from datetime import datetime, timezone

    conv.updated_at = datetime.now(timezone.utc)
    if not (conv.title or "").strip():
        t = body.message.strip().replace("\n", " ")
        conv.title = (t[:48] + "…") if len(t) > 48 else t

    await reap_stale_running_jobs(session)
    active = await conversation_has_active_chat_job(session, conv.id)
    if active is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "message": "W tej rozmowie trwa już zadanie. Poczekaj na jego zakończenie.",
                "job_id": str(active.id),
                "conversation_id": str(conv.id),
            },
        )

    session.add(
        MessageORM(
            id=uuid4(),
            conversation_id=conv.id,
            role="user",
            content=body.message,
        )
    )

    job = await create_job(
        session,
        user_id=user.id,
        kind="chat",
        payload=body.model_dump(mode="json"),
        conversation_id=conv.id,
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        active = await conversation_has_active_chat_job(session, conv.id)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "message": "W tej rozmowie trwa już zadanie. Poczekaj na jego zakończenie.",
                "job_id": str(active.id) if active is not None else None,
                "conversation_id": str(conv.id),
            },
        ) from None

    asyncio.create_task(run_chat_job(job.id, user.id, body))

    accepted = ChatAcceptedResponse(job_id=job.id, conversation_id=conv.id)
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=accepted.model_dump(mode="json"))
