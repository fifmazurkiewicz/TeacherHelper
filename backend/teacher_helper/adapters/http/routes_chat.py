from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from teacher_helper.adapters.http.deps import CurrentUser, DbSession
from teacher_helper.adapters.http.rate_limit import check_rate_limit
from teacher_helper.adapters.http.schemas import ChatAcceptedResponse, ChatRequest
from teacher_helper.config import get_settings
from teacher_helper.infrastructure.alert_webhook import send_alert_webhook
from teacher_helper.infrastructure.db.models import ConversationORM, MessageORM, ProjectORM
from teacher_helper.infrastructure.db.session import async_session_factory
from teacher_helper.infrastructure.jobs import create_job
from teacher_helper.infrastructure.system_incidents import record_system_incident
from teacher_helper.infrastructure.usage_limits import (
    effective_user_llm_daily_token_limit,
    sum_llm_total_tokens_today,
    sum_llm_total_tokens_today_for_user,
)
from teacher_helper.use_cases.chat_job_runner import run_chat_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/chat", tags=["chat"])


@router.post("", response_model=ChatAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def chat(session: DbSession, user: CurrentUser, body: ChatRequest) -> JSONResponse:
    await check_rate_limit(session, user)
    s = get_settings()
    tokens_today = await sum_llm_total_tokens_today(session, include_dry_run=False)
    if s.llm_daily_token_hard_limit is not None and tokens_today >= s.llm_daily_token_hard_limit:
        async with async_session_factory() as inc_sess:
            await record_system_incident(
                inc_sess,
                event_type="llm_hard_limit_blocked",
                severity="critical",
                title="Żądanie czatu zablokowane — dzienny limit tokenów",
                detail={"tokens_today": tokens_today, "hard_limit": s.llm_daily_token_hard_limit},
                user_id=user.id,
            )
            await inc_sess.commit()
        await send_alert_webhook(
            {
                "event": "llm_hard_limit_blocked",
                "severity": "critical",
                "tokens_today": tokens_today,
                "hard_limit": s.llm_daily_token_hard_limit,
                "user_id": str(user.id),
            }
        )
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Dzienny limit tokenów LLM został wyczerpany. Skontaktuj się z administratorem lub spróbuj jutro (UTC).",
        )

    eff_user_daily = effective_user_llm_daily_token_limit(user, s)
    if eff_user_daily is not None:
        user_tokens_today = await sum_llm_total_tokens_today_for_user(session, user.id, include_dry_run=False)
        if user_tokens_today >= eff_user_daily:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    "Osiągnięto dzienny limit tokenów LLM dla Twojego konta (UTC). "
                    "Skontaktuj się z administratorem lub spróbuj jutro."
                ),
            )

    if body.conversation_id is not None:
        conv = await session.get(ConversationORM, body.conversation_id)
        if not conv or conv.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rozmowa nie znaleziona")
    else:
        conv = ConversationORM(id=uuid4(), user_id=user.id, title="")
        session.add(conv)
        await session.flush()

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
    await session.commit()

    asyncio.create_task(run_chat_job(job.id, user.id, body))

    accepted = ChatAcceptedResponse(job_id=job.id, conversation_id=conv.id)
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=accepted.model_dump(mode="json"))
