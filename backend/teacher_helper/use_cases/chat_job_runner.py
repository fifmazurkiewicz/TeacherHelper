from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select

from teacher_helper.adapters.http.chat_services import _llm_summary, message_pair_for_orchestrator_llm
from teacher_helper.adapters.http.chat_services import orchestrator as _orchestrator
from teacher_helper.adapters.http.schemas import ChatRequest, CreatedFileBrief
from teacher_helper.infrastructure.alert_webhook import send_alert_webhook
from teacher_helper.infrastructure.db.llm_usage import LangfuseTraceContext
from teacher_helper.infrastructure.db.models import ConversationORM, FileAssetORM, MessageORM
from teacher_helper.infrastructure.db.session import async_session_factory
from teacher_helper.infrastructure.jobs import get_job, mark_job_done, mark_job_error, mark_job_running
from teacher_helper.infrastructure.system_incidents import record_system_incident
from teacher_helper.use_cases.conversation_context import build_history_with_rolling_summary, cap_orchestrator_history

logger = logging.getLogger(__name__)


async def run_chat_job(job_id: UUID, user_id: UUID, body: ChatRequest) -> None:
    async with async_session_factory() as session:
        job = await get_job(session, job_id)
        if job is None or job.user_id != user_id:
            return
        conv_id = job.conversation_id
        if conv_id is None:
            await mark_job_error(session, job_id, "Brak conversation_id w zadaniu")
            await session.commit()
            return

        try:
            await mark_job_running(session, job_id)
            await session.commit()

            conv = await session.get(ConversationORM, conv_id)
            if conv is None or conv.user_id != user_id:
                raise ValueError("Rozmowa nie znaleziona")

            stmt = (
                select(MessageORM)
                .where(MessageORM.conversation_id == conv.id)
                .order_by(MessageORM.created_at.asc())
            )
            prior_msgs = list((await session.scalars(stmt)).all())

            trace_context = LangfuseTraceContext(
                conversation_id=conv.id,
                project_id=conv.project_id,
                job_id=job_id,
            )

            if body.history and len(prior_msgs) <= 1:
                history = cap_orchestrator_history(
                    [(h.role, h.content) for h in body.history if h.role in ("user", "assistant")],
                )
            else:
                history = await build_history_with_rolling_summary(
                    session,
                    user_id=user_id,
                    conv=conv,
                    prior_msgs=prior_msgs,
                    message_pair_for_llm=message_pair_for_orchestrator_llm,
                    summary_llm=_llm_summary,
                    dry_run=body.dry_run,
                    trace_context=trace_context,
                )

            result = await _orchestrator.execute(
                session,
                user_id,
                body.message,
                project_id=conv.project_id,
                attached_file_ids=body.attached_file_ids,
                history=history,
                dry_run=body.dry_run,
                trace_context=trace_context,
            )

            now = datetime.now(timezone.utc)
            conv.updated_at = now
            if result.linked_project_id is not None:
                conv.project_id = result.linked_project_id

            created_files_list: list[CreatedFileBrief] = []
            if result.created_file_ids:
                stmt_cf = select(FileAssetORM).where(
                    FileAssetORM.user_id == user_id,
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

            payload = {
                "reply": result.reply,
                "conversation_id": str(conv.id),
                "created_file_ids": [str(x) for x in result.created_file_ids],
                "run_modules": list(result.run_modules),
                "created_files": [cf.model_dump(mode="json") for cf in created_files_list],
                "needs_clarification": result.needs_clarification,
                "clarification_question": result.clarification_question,
                "dry_run": result.dry_run,
                "side_effects_skipped": result.side_effects_skipped,
                "linked_project_id": str(result.linked_project_id) if result.linked_project_id else None,
                "pending_project_creation": result.pending_project_creation,
                "pending_project_deletion": result.pending_project_deletion,
            }
            await mark_job_done(session, job_id, payload)
            await session.commit()
        except Exception as exc:
            logger.error("Chat job %s failed: %s\n%s", job_id, exc, traceback.format_exc())
            async with async_session_factory() as err_sess:
                await mark_job_error(err_sess, job_id, str(exc))
                await record_system_incident(
                    err_sess,
                    event_type="chat_job_error",
                    severity="critical",
                    title="Błąd zadania czatu w tle",
                    detail={"error": str(exc)[:2000], "job_id": str(job_id)},
                    user_id=user_id,
                )
                await err_sess.commit()
            await send_alert_webhook(
                {
                    "event": "chat_job_error",
                    "severity": "critical",
                    "message": str(exc)[:800],
                    "user_id": str(user_id),
                    "job_id": str(job_id),
                }
            )
