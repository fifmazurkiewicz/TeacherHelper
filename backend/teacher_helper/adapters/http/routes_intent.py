from __future__ import annotations

import json

from fastapi import APIRouter

from teacher_helper.adapters.http.deps import CurrentUser, DbSession
from teacher_helper.adapters.http.schemas import AnalyzeIntentRequest
from teacher_helper.infrastructure.db.llm_usage import record_llm_usage_event
from teacher_helper.infrastructure.factories import build_llm_client
from teacher_helper.use_cases.chat_orchestrator import ORCHESTRATOR_SYSTEM, parse_orchestration_json

router = APIRouter(prefix="/v1/intent", tags=["intent"])
_llm = build_llm_client()


@router.post("/analyze")
async def analyze_intent(session: DbSession, user: CurrentUser, body: AnalyzeIntentRequest) -> dict:
    """Lekki endpoint diagnostyczny — ten sam kontrakt JSON co orchestrator."""
    user_text = body.message.strip()
    comp = await _llm.complete(ORCHESTRATOR_SYSTEM, user_text)
    await record_llm_usage_event(
        session,
        user_id=user.id,
        call_kind="intent_analyze",
        module_name=None,
        completion=comp,
        system_text=ORCHESTRATOR_SYSTEM,
        user_text=user_text,
    )
    await session.commit()
    plan = parse_orchestration_json(comp.text)
    return {
        "summary": plan["assistant_reply"],
        "suggested_modules": plan["run_modules"],
        "needs_clarification": plan["needs_clarification"],
        "raw_json": json.dumps(plan, ensure_ascii=False),
    }
