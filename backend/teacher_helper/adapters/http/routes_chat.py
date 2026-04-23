from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from teacher_helper.adapters.http.deps import CurrentUser, DbSession
from teacher_helper.adapters.http.rate_limit import check_rate_limit
from teacher_helper.adapters.http.schemas import ChatRequest, ChatResponse, CreatedFileBrief, PendingProjectAction
from teacher_helper.config import get_settings
from teacher_helper.infrastructure.alert_webhook import send_alert_webhook
from teacher_helper.infrastructure.db.models import ConversationORM, FileAssetORM, MessageORM, ProjectORM
from teacher_helper.infrastructure.db.session import async_session_factory
from teacher_helper.infrastructure.factories import (
    build_image_generator,
    build_llm_client,
    build_lyria_music_generator,
    build_module_llm_client,
    build_music_generator,
    build_sound_generator,
    build_summary_llm_client,
    build_video_generator,
)
from teacher_helper.infrastructure.storage.local import LocalStorage
from teacher_helper.infrastructure.system_incidents import record_system_incident
from teacher_helper.infrastructure.usage_limits import (
    effective_user_llm_daily_token_limit,
    sum_llm_total_tokens_today,
    sum_llm_total_tokens_today_for_user,
)
from teacher_helper.use_cases.chat_orchestrator import ChatOrchestratorUseCase
from teacher_helper.use_cases.conversation_context import build_history_with_rolling_summary, cap_orchestrator_history

logger = logging.getLogger(__name__)


async def _await_or_cancel_on_disconnect(
    request: Request,
    orchestrator_task: asyncio.Task[Any],
    *,
    user_id: Any,
) -> Any:
    """Kończy oczekiwanie na orchestrator; przy rozłączeniu klienta anuluje zadanie (asyncio.cancel)."""
    poll_s = 0.25
    while not orchestrator_task.done():
        if await request.is_disconnected():
            orchestrator_task.cancel()
            try:
                await orchestrator_task
            except asyncio.CancelledError:
                logger.info("Orchestrator anulowany — rozłączenie klienta (user=%s)", user_id)
            raise HTTPException(
                status_code=499,
                detail="Przerwano na pro\u015bb\u0119 u\u017cytkownika (roz\u0142\u0105czenie).",
            )
        await asyncio.sleep(poll_s)
    return await orchestrator_task


def _message_pair_for_orchestrator_llm(m: MessageORM) -> tuple[str, str]:
    """Treść wiadomości dla kontekstu LLM — dla asystenta dokleja podsumowanie utworzonych plików z ``extra``."""
    role = m.role
    content = (m.content or "").strip()
    if role != "assistant":
        return (role, content)
    extra = m.extra
    if not isinstance(extra, dict):
        return (role, content)
    annex: list[str] = []
    mods = extra.get("run_modules")
    if isinstance(mods, list) and mods:
        parts = [str(x).strip() for x in mods if x]
        if parts:
            annex.append("[W tej odpowiedzi wygenerowano moduły: " + ", ".join(parts) + ".]")
    files = extra.get("created_files")
    if isinstance(files, list) and files:
        names: list[str] = []
        for item in files[:35]:
            if isinstance(item, dict) and item.get("name"):
                names.append(str(item["name"]))
            elif isinstance(item, str) and item.strip():
                names.append(item.strip())
        if names:
            annex.append("[Pliki zapisane w bibliotece:\n" + "\n".join(f"  • {n}" for n in names) + "]")
    if annex:
        content = content + "\n\n" + "\n".join(annex)
    return (role, content)


router = APIRouter(prefix="/v1/chat", tags=["chat"])
_llm = build_llm_client()
_llm_summary = build_summary_llm_client()
_llm_modules = build_module_llm_client()
_storage = LocalStorage()
_image_gen = build_image_generator()
_video_gen = build_video_generator()
_music_gen = build_music_generator()
_sound_gen = build_sound_generator()
_lyria_music = build_lyria_music_generator()
_orchestrator = ChatOrchestratorUseCase(
    _llm, _storage,
    image_gen=_image_gen,
    video_gen=_video_gen,
    music_gen=_music_gen,
    sound_gen=_sound_gen,
    lyria_music=_lyria_music,
    llm_modules=_llm_modules,
)

logger.debug(
    "Chat route initialised: llm=%s, llm_modules=%s, image_gen=%s, video_gen=%s, music_gen=%s, sound_gen=%s, lyria_music=%s",
    type(_llm).__name__, type(_llm_modules).__name__,
    type(_image_gen).__name__ if _image_gen else None,
    type(_video_gen).__name__ if _video_gen else None,
    type(_music_gen).__name__ if _music_gen else None,
    type(_sound_gen).__name__ if _sound_gen else None,
    type(_lyria_music).__name__ if _lyria_music else None,
)


@router.post("", response_model=ChatResponse)
async def chat(
    request: Request,
    session: DbSession,
    user: CurrentUser,
    body: ChatRequest,
) -> ChatResponse:
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

    stmt = (
        select(MessageORM)
        .where(MessageORM.conversation_id == conv.id)
        .order_by(MessageORM.created_at.asc())
    )
    prior_msgs = list((await session.scalars(stmt)).all())

    if body.history and not prior_msgs:
        history = cap_orchestrator_history(
            [(h.role, h.content) for h in body.history if h.role in ("user", "assistant")],
        )
    else:
        history = await build_history_with_rolling_summary(
            session,
            user_id=user.id,
            conv=conv,
            prior_msgs=prior_msgs,
            message_pair_for_llm=_message_pair_for_orchestrator_llm,
            summary_llm=_llm_summary,
            dry_run=body.dry_run,
        )

    effective_project = conv.project_id

    logger.debug(
        "POST /v1/chat — user=%s conv=%s project=%s msg_len=%d history=%d dry_run=%s",
        user.id, conv.id, effective_project, len(body.message), len(history), body.dry_run,
    )
    orchestrator_task = asyncio.create_task(
        _orchestrator.execute(
            session,
            user.id,
            body.message,
            project_id=effective_project,
            attached_file_ids=body.attached_file_ids,
            history=history,
            dry_run=body.dry_run,
        )
    )
    try:
        result = await _await_or_cancel_on_disconnect(
            request, orchestrator_task, user_id=user.id
        )
    except HTTPException:
        raise
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
