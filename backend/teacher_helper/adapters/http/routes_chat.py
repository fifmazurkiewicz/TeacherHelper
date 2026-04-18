from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from teacher_helper.adapters.http.deps import CurrentUser, DbSession
from teacher_helper.adapters.http.rate_limit import check_rate_limit
from teacher_helper.adapters.http.schemas import ChatRequest, ChatResponse, CreatedFileBrief, PendingProjectAction
from teacher_helper.config import get_settings
from teacher_helper.infrastructure.alert_webhook import send_alert_webhook
from teacher_helper.infrastructure.db.models import ConversationORM, FileAssetORM, MessageORM
from teacher_helper.infrastructure.db.session import async_session_factory
from teacher_helper.infrastructure.factories import (
    build_image_generator,
    build_llm_client,
    build_module_llm_client,
    build_music_generator,
    build_video_generator,
)
from teacher_helper.infrastructure.storage.local import LocalStorage
from teacher_helper.infrastructure.system_incidents import record_system_incident
from teacher_helper.infrastructure.usage_limits import sum_llm_total_tokens_today
from teacher_helper.use_cases.chat_orchestrator import ChatOrchestratorUseCase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/chat", tags=["chat"])
_llm = build_llm_client()
_llm_modules = build_module_llm_client()
_storage = LocalStorage()
_image_gen = build_image_generator()
_video_gen = build_video_generator()
_music_gen = build_music_generator()
_orchestrator = ChatOrchestratorUseCase(
    _llm, _storage,
    image_gen=_image_gen,
    video_gen=_video_gen,
    music_gen=_music_gen,
    llm_modules=_llm_modules,
)

logger.debug(
    "Chat route initialised: llm=%s, llm_modules=%s, image_gen=%s, video_gen=%s, music_gen=%s",
    type(_llm).__name__, type(_llm_modules).__name__,
    type(_image_gen).__name__ if _image_gen else None,
    type(_video_gen).__name__ if _video_gen else None,
    type(_music_gen).__name__ if _music_gen else None,
)


@router.post("", response_model=ChatResponse)
async def chat(session: DbSession, user: CurrentUser, body: ChatRequest) -> ChatResponse:
    check_rate_limit(user)
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

    if body.conversation_id is not None:
        conv = await session.get(ConversationORM, body.conversation_id)
        if not conv or conv.user_id != user.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Rozmowa nie znaleziona")
    else:
        conv = ConversationORM(id=uuid4(), user_id=user.id, title="")
        session.add(conv)
        await session.flush()

    stmt = (
        select(MessageORM)
        .where(MessageORM.conversation_id == conv.id)
        .order_by(MessageORM.created_at.asc())
    )
    prior_msgs = list((await session.scalars(stmt)).all())
    history_db: list[tuple[str, str]] = []
    for m in prior_msgs[-40:]:
        if m.role in ("user", "assistant"):
            history_db.append((m.role, m.content))

    if body.history and not prior_msgs:
        history = [(h.role, h.content) for h in body.history[-20:]]
    else:
        history = history_db

    effective_project = body.project_id if body.project_id is not None else conv.project_id

    logger.debug(
        "POST /v1/chat — user=%s conv=%s project=%s msg_len=%d history=%d dry_run=%s",
        user.id, conv.id, effective_project, len(body.message), len(history), body.dry_run,
    )
    try:
        result = await _orchestrator.execute(
            session,
            user.id,
            body.message,
            project_id=effective_project,
            attached_file_ids=body.attached_file_ids,
            history=history,
            dry_run=body.dry_run,
        )
    except Exception as e:
        logger.error(
            "Chat orchestrator error for user=%s: %s\n%s",
            user.id, e, traceback.format_exc(),
        )
        async with async_session_factory() as inc_sess:
            await record_system_incident(
                inc_sess,
                event_type="llm_upstream_error",
                severity="critical",
                title="Błąd wywołania modelu językowego",
                detail={"error": str(e)[:2000], "traceback": traceback.format_exc()[:3000]},
                user_id=user.id,
            )
            await inc_sess.commit()
        await send_alert_webhook(
            {
                "event": "llm_upstream_error",
                "severity": "critical",
                "message": str(e)[:800],
                "user_id": str(user.id),
            }
        )
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"Model językowy nie odpowiedział poprawnie. Administrator został powiadomiony. Szczegóły: {e!s:.300}",
        ) from e

    now = datetime.now(timezone.utc)
    conv.updated_at = now
    if not (conv.title or "").strip():
        t = body.message.strip().replace("\n", " ")
        conv.title = (t[:48] + "…") if len(t) > 48 else t
    if result.linked_project_id is not None:
        conv.project_id = result.linked_project_id

    session.add(
        MessageORM(
            id=uuid4(),
            conversation_id=conv.id,
            role="user",
            content=body.message,
        )
    )
    created_files_list: list[CreatedFileBrief] = []
    if result.created_file_ids:
        stmt_cf = select(FileAssetORM).where(
            FileAssetORM.user_id == user.id,
            FileAssetORM.id.in_(result.created_file_ids),
        )
        row_map = {r.id: r for r in (await session.scalars(stmt_cf)).all()}
        for fid in result.created_file_ids:
            r = row_map.get(fid)
            if r:
                created_files_list.append(CreatedFileBrief(id=r.id, name=r.name, mime_type=r.mime_type))

    extra: dict | None = None
    if result.created_file_ids or result.run_modules:
        extra = {
            "created_file_ids": [str(x) for x in result.created_file_ids],
            "run_modules": list(result.run_modules),
            "created_files": [cf.model_dump(mode="json") for cf in created_files_list],
        }
    session.add(
        MessageORM(
            id=uuid4(),
            conversation_id=conv.id,
            role="assistant",
            content=result.reply,
            extra=extra,
        )
    )

    await session.commit()
    return ChatResponse(
        reply=result.reply,
        conversation_id=conv.id,
        created_file_ids=result.created_file_ids,
        run_modules=result.run_modules,
        created_files=created_files_list,
        needs_clarification=result.needs_clarification,
        clarification_question=result.clarification_question,
        dry_run=result.dry_run,
        side_effects_skipped=result.side_effects_skipped,
        linked_project_id=result.linked_project_id,
        pending_project_creation=(
            PendingProjectAction.model_validate(result.pending_project_creation)
            if result.pending_project_creation
            else None
        ),
        pending_project_deletion=(
            PendingProjectAction.model_validate(result.pending_project_deletion)
            if result.pending_project_deletion
            else None
        ),
    )
