from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from teacher_helper.adapters.http.deps import AdminUser, DbSession
from teacher_helper.config import get_settings
from teacher_helper.infrastructure.alert_webhook import send_alert_webhook
from teacher_helper.infrastructure.db.models import AiReadAuditORM, FileAssetORM, LlmUsageLogORM, UserORM
from teacher_helper.infrastructure.system_incidents import (
    count_recent_incidents,
    list_recent_incidents,
    record_system_incident,
)
from teacher_helper.infrastructure.usage_limits import (
    build_limit_alerts,
    per_user_llm_token_stats,
    sum_llm_total_tokens_today,
)
from teacher_helper.security import hash_password

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def _check_admin_key(x_admin_key: str | None) -> None:
    s = get_settings()
    if s.admin_api_key and x_admin_key != s.admin_api_key:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Nieprawidłowy X-Admin-Key")


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

class AdminUserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    role: str
    rate_limit_rpm: int | None
    llm_daily_token_limit: int | None
    effective_llm_daily_token_limit: int | None
    uses_site_default_llm_daily_limit: bool
    created_at: datetime


def _admin_user_response(u: UserORM) -> AdminUserResponse:
    s = get_settings()
    raw = u.llm_daily_token_limit
    if raw is None:
        eff: int | None = int(s.default_user_llm_daily_token_limit)
        uses_default = True
    elif raw == 0:
        eff = None
        uses_default = False
    else:
        eff = int(raw)
        uses_default = False
    return AdminUserResponse(
        id=u.id,
        email=u.email,
        display_name=u.display_name,
        role=u.role.value,
        rate_limit_rpm=u.rate_limit_rpm,
        llm_daily_token_limit=raw,
        effective_llm_daily_token_limit=eff,
        uses_site_default_llm_daily_limit=uses_default,
        created_at=u.created_at,
    )


class UpdateUserRequest(BaseModel):
    rate_limit_rpm: int | None = Field(None, ge=1, le=10000)
    # 0 = brak limitu per konto (tylko limity globalne); NULL w bazie = domyślny z DEFAULT_USER_LLM_DAILY_TOKEN_LIMIT
    llm_daily_token_limit: int | None = Field(None, ge=0, le=2_000_000_000)
    role: str | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    session: DbSession,
    user: AdminUser,
    x_admin_key: str | None = Header(None, alias="X-Admin-Key"),
) -> list[AdminUserResponse]:
    _check_admin_key(x_admin_key)
    stmt = select(UserORM).order_by(UserORM.created_at.desc())
    rows = list((await session.scalars(stmt)).all())
    return [_admin_user_response(u) for u in rows]


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    session: DbSession,
    admin: AdminUser,
    user_id: UUID,
    body: UpdateUserRequest,
    x_admin_key: str | None = Header(None, alias="X-Admin-Key"),
) -> AdminUserResponse:
    _check_admin_key(x_admin_key)
    target = await session.get(UserORM, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Użytkownik nie znaleziony")

    if body.role is not None:
        from teacher_helper.infrastructure.db.models import UserRole
        try:
            target.role = UserRole(body.role)
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Nieprawidłowa rola: {body.role}")

    if body.rate_limit_rpm is not None:
        target.rate_limit_rpm = body.rate_limit_rpm

    updates = body.model_dump(exclude_unset=True)
    if "llm_daily_token_limit" in updates:
        target.llm_daily_token_limit = updates["llm_daily_token_limit"]

    await session.commit()
    await session.refresh(target)
    return _admin_user_response(target)


@router.delete("/users/{user_id}/rate-limit", response_model=AdminUserResponse)
async def clear_user_rate_limit(
    session: DbSession,
    admin: AdminUser,
    user_id: UUID,
    x_admin_key: str | None = Header(None, alias="X-Admin-Key"),
) -> AdminUserResponse:
    """Przywraca globalny domyślny rate limit (usuwa indywidualny)."""
    _check_admin_key(x_admin_key)
    target = await session.get(UserORM, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Użytkownik nie znaleziony")
    target.rate_limit_rpm = None
    await session.commit()
    await session.refresh(target)
    return _admin_user_response(target)


@router.delete("/users/{user_id}/llm-daily-token-limit", response_model=AdminUserResponse)
async def clear_user_llm_daily_token_limit(
    session: DbSession,
    admin: AdminUser,
    user_id: UUID,
    x_admin_key: str | None = Header(None, alias="X-Admin-Key"),
) -> AdminUserResponse:
    """Usuwa indywidualny limit — obowiązuje domyślny z konfiguracji (DEFAULT_USER_LLM_DAILY_TOKEN_LIMIT)."""
    _check_admin_key(x_admin_key)
    target = await session.get(UserORM, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Użytkownik nie znaleziony")
    target.llm_daily_token_limit = None
    await session.commit()
    await session.refresh(target)
    return _admin_user_response(target)


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    session: DbSession,
    admin: AdminUser,
    user_id: UUID,
    body: ResetPasswordRequest,
    x_admin_key: str | None = Header(None, alias="X-Admin-Key"),
) -> dict:
    _check_admin_key(x_admin_key)
    target = await session.get(UserORM, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Użytkownik nie znaleziony")
    target.hashed_password = hash_password(body.new_password)
    await session.commit()
    return {"status": "ok", "user_id": str(user_id), "message": "Hasło zostało zresetowane."}


# ---------------------------------------------------------------------------
# Stats / monitoring (existing)
# ---------------------------------------------------------------------------

@router.get("/stats")
async def admin_stats(
    session: DbSession,
    user: AdminUser,
    x_admin_key: str | None = Header(None, alias="X-Admin-Key"),
) -> dict:
    _check_admin_key(x_admin_key)
    users = await session.scalar(select(func.count()).select_from(UserORM))
    files = await session.scalar(select(func.count()).select_from(FileAssetORM))
    audits = await session.scalar(select(func.count()).select_from(AiReadAuditORM))
    return {
        "users": users or 0,
        "files": files or 0,
        "ai_read_audits": audits or 0,
    }


@router.get("/monitoring")
async def admin_monitoring(
    session: DbSession,
    user: AdminUser,
    x_admin_key: str | None = Header(None, alias="X-Admin-Key"),
) -> dict:
    _check_admin_key(x_admin_key)
    s = get_settings()

    users = await session.scalar(select(func.count()).select_from(UserORM))
    files = await session.scalar(select(func.count()).select_from(FileAssetORM))
    audits = await session.scalar(select(func.count()).select_from(AiReadAuditORM))

    total_calls = await session.scalar(select(func.count()).select_from(LlmUsageLogORM)) or 0
    sum_prompt = await session.scalar(select(func.coalesce(func.sum(LlmUsageLogORM.prompt_tokens), 0))) or 0
    sum_completion = await session.scalar(select(func.coalesce(func.sum(LlmUsageLogORM.completion_tokens), 0))) or 0
    sum_total = await session.scalar(select(func.coalesce(func.sum(LlmUsageLogORM.total_tokens), 0))) or 0

    by_model_rows = await session.execute(
        select(
            LlmUsageLogORM.model,
            LlmUsageLogORM.provider,
            func.count(LlmUsageLogORM.id).label("calls"),
            func.coalesce(func.sum(LlmUsageLogORM.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(LlmUsageLogORM.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(LlmUsageLogORM.total_tokens), 0).label("total_tokens"),
        )
        .group_by(LlmUsageLogORM.model, LlmUsageLogORM.provider)
        .order_by(func.count(LlmUsageLogORM.id).desc())
    )
    by_model = [
        {
            "model": r.model, "provider": r.provider, "calls": int(r.calls),
            "prompt_tokens": int(r.prompt_tokens), "completion_tokens": int(r.completion_tokens),
            "total_tokens": int(r.total_tokens),
        }
        for r in by_model_rows.all()
    ]

    by_route_rows = await session.execute(
        select(
            LlmUsageLogORM.call_kind, LlmUsageLogORM.module_name,
            func.count(LlmUsageLogORM.id).label("calls"),
            func.coalesce(func.sum(LlmUsageLogORM.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(LlmUsageLogORM.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(LlmUsageLogORM.total_tokens), 0).label("total_tokens"),
        )
        .group_by(LlmUsageLogORM.call_kind, LlmUsageLogORM.module_name)
        .order_by(LlmUsageLogORM.call_kind, LlmUsageLogORM.module_name)
    )
    by_call_route = [
        {
            "call_kind": r.call_kind, "module_name": r.module_name, "calls": int(r.calls),
            "prompt_tokens": int(r.prompt_tokens), "completion_tokens": int(r.completion_tokens),
            "total_tokens": int(r.total_tokens),
        }
        for r in by_route_rows.all()
    ]

    langfuse_on = bool(s.langfuse_public_key and s.langfuse_secret_key)
    tokens_today = await sum_llm_total_tokens_today(session, include_dry_run=False)
    limit_alerts = build_limit_alerts(tokens_today)
    has_critical_limit = any(a.get("severity") == "critical" for a in limit_alerts)
    if has_critical_limit and s.alert_webhook_url:
        since = datetime.now(timezone.utc) - timedelta(minutes=15)
        sent = await count_recent_incidents(session, event_type="alert_webhook_llm_limit", since=since)
        if sent == 0:
            await record_system_incident(
                session, event_type="alert_webhook_llm_limit", severity="info",
                title="Wysłano webhook (przekroczenie limitu LLM)",
                detail={"alerts": limit_alerts, "tokens_today": tokens_today},
            )
            await send_alert_webhook({"event": "llm_limit_critical", "severity": "critical", "tokens_today": tokens_today, "alerts": limit_alerts})
            await session.commit()
    incidents = await list_recent_incidents(session, limit=40)
    per_user_tokens = await per_user_llm_token_stats(session)

    return {
        "application": {"users": users or 0, "files": files or 0, "ai_read_audits": audits or 0},
        "alerts": {
            "operational": limit_alerts, "tokens_today_utc": tokens_today,
            "soft_limit": s.llm_daily_token_soft_limit, "hard_limit": s.llm_daily_token_hard_limit,
            "webhook_configured": bool(s.alert_webhook_url),
            "hint": "Alerty limitów są odświeżane przy każdym GET /v1/admin/monitoring; webhook dla sytuacji krytycznej max. raz na 15 min.",
        },
        "recent_incidents": [
            {"id": str(i.id), "event_type": i.event_type, "severity": i.severity, "title": i.title,
             "detail_json": i.detail_json, "user_id": str(i.user_id) if i.user_id else None,
             "created_at": i.created_at.isoformat() if i.created_at else None}
            for i in incidents
        ],
        "llm_usage": {
            "total_calls": int(total_calls), "total_prompt_tokens": int(sum_prompt),
            "total_completion_tokens": int(sum_completion), "total_tokens_recorded": int(sum_total),
            "by_model": by_model, "by_call_kind_and_module": by_call_route,
            "description": "Każde wywołanie LLM jest zapisywane w tabeli llm_usage_log. Tokeny pochodzą z odpowiedzi API; stub nie raportuje tokenów.",
        },
        "langfuse": {
            "enabled": langfuse_on, "host": s.langfuse_host, "dashboard_url": s.langfuse_host.rstrip("/") + "/",
            "hint": ("Langfuse włączony — generacje trafiają do dashboard." if langfuse_on
                     else "Uzupełnij LANGFUSE_* w .env, aby duplikować zdarzenia LLM do chmurowego observability."),
        },
        "langgraph": {"role": "LangGraph — w przyszłości orchestrator można przenieść do LangGraph."},
        "per_user_llm_tokens": per_user_tokens,
        "per_user_llm_tokens_hint": (
            "Tokeny bez dry-run. „Dziś” i „miesiąc” — kalendarz UTC. "
            "Limit / dzień: własny, domyślny (DEFAULT_USER_LLM_DAILY_TOKEN_LIMIT) lub brak (wartość 0 w bazie = tylko limity globalne). "
            "POST /v1/chat."
        ),
    }


@router.post("/alerts/test-webhook")
async def admin_test_webhook(
    _session: DbSession, user: AdminUser,
    x_admin_key: str | None = Header(None, alias="X-Admin-Key"),
) -> dict:
    _check_admin_key(x_admin_key)
    s = get_settings()
    if not s.alert_webhook_url:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Brak ALERT_WEBHOOK_URL w konfiguracji")
    ok = await send_alert_webhook({"event": "test", "severity": "info", "message": "TeacherHelper — test webhooka z panelu admina"})
    return {"sent": ok, "url_configured": True}
