from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from teacher_helper.adapters.http.deps import AdminUser, DbSession
from teacher_helper.config import get_settings
from teacher_helper.infrastructure.alert_webhook import send_alert_webhook
from teacher_helper.infrastructure.db.llm_usage import langfuse_auth_check_sync, send_langfuse_test_event_sync
from teacher_helper.infrastructure.db.models import AiReadAuditORM, FileAssetORM, LlmUsageLogORM, UserORM
from teacher_helper.infrastructure.system_incidents import (
    count_recent_incidents,
    list_recent_incidents,
    record_system_incident,
)
from teacher_helper.infrastructure.usage_limits import (
    build_limit_alerts,
    llm_usage_month_by_user_id,
    per_user_llm_cost_stats,
    sum_llm_cost_usd_month,
    user_llm_usage_month,
)
from teacher_helper.security import hash_password

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def _check_admin_key(x_admin_key: str | None) -> None:
    """Optional machine key. Browser admin uses JWT role; missing header is allowed."""
    s = get_settings()
    if not s.admin_api_key:
        return
    incoming = (x_admin_key or "").strip()
    if not incoming:
        return
    if incoming != s.admin_api_key:
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
    llm_monthly_cost_limit_usd: float | None
    effective_llm_monthly_cost_limit_usd: float | None
    uses_site_default_llm_monthly_limit: bool
    llm_cost_month_usd: float = 0.0
    llm_tokens_month: int = 0
    llm_monthly_limit_reached: bool = False
    is_approved: bool = False
    created_at: datetime


def _admin_user_response(
    u: UserORM,
    *,
    llm_cost_month_usd: float = 0.0,
    llm_tokens_month: int = 0,
) -> AdminUserResponse:
    s = get_settings()
    raw = u.llm_monthly_cost_limit_usd
    if raw is None:
        eff: float | None = float(s.default_user_llm_monthly_cost_limit_usd)
        uses_default = True
    elif raw == 0:
        eff = None
        uses_default = False
    else:
        eff = float(raw)
        uses_default = False
    limit_reached = eff is not None and llm_cost_month_usd >= eff
    return AdminUserResponse(
        id=u.id,
        email=u.email,
        display_name=u.display_name,
        role=u.role.value,
        rate_limit_rpm=u.rate_limit_rpm,
        llm_monthly_cost_limit_usd=float(raw) if raw is not None else None,
        effective_llm_monthly_cost_limit_usd=eff,
        uses_site_default_llm_monthly_limit=uses_default,
        llm_cost_month_usd=llm_cost_month_usd,
        llm_tokens_month=llm_tokens_month,
        llm_monthly_limit_reached=limit_reached,
        is_approved=u.is_approved,
        created_at=u.created_at,
    )


class UpdateUserRequest(BaseModel):
    rate_limit_rpm: int | None = Field(None, ge=1, le=10000)
    # 0 = brak limitu per konto (tylko limity globalne); NULL w bazie = domyślny z DEFAULT_USER_LLM_MONTHLY_COST_LIMIT_USD
    llm_monthly_cost_limit_usd: float | None = Field(None, ge=0, le=100_000.0)
    role: str | None = None
    is_approved: bool | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


def assert_can_set_approval(admin: UserORM, target: UserORM, is_approved: bool) -> None:
    if admin.id == target.id and not is_approved:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Nie można cofnąć dostępu własnego konta")


async def _admin_user_response_with_usage(session: DbSession, u: UserORM) -> AdminUserResponse:
    row = await user_llm_usage_month(session, u.id)
    return _admin_user_response(
        u,
        llm_cost_month_usd=float(row["cost_month_usd"]),
        llm_tokens_month=int(row["tokens_month"]),
    )


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    session: DbSession,
    user: AdminUser,
    x_admin_key: str | None = Header(None, alias="X-Admin-Key"),
) -> list[AdminUserResponse]:
    _check_admin_key(x_admin_key)
    stmt = select(UserORM).order_by(UserORM.created_at.desc())
    rows = list((await session.scalars(stmt)).all())
    usage_by_user = await llm_usage_month_by_user_id(session)
    return [
        _admin_user_response(
            u,
            llm_cost_month_usd=float(usage_by_user.get(u.id, {}).get("cost_month_usd", 0)),
            llm_tokens_month=int(usage_by_user.get(u.id, {}).get("tokens_month", 0)),
        )
        for u in rows
    ]


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
    if "llm_monthly_cost_limit_usd" in updates:
        target.llm_monthly_cost_limit_usd = updates["llm_monthly_cost_limit_usd"]
    if "is_approved" in updates and updates["is_approved"] is not None:
        assert_can_set_approval(admin, target, bool(updates["is_approved"]))
        target.is_approved = bool(updates["is_approved"])

    await session.commit()
    await session.refresh(target)
    return await _admin_user_response_with_usage(session, target)


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
    return await _admin_user_response_with_usage(session, target)


@router.delete("/users/{user_id}/llm-monthly-cost-limit", response_model=AdminUserResponse)
async def clear_user_llm_monthly_cost_limit(
    session: DbSession,
    admin: AdminUser,
    user_id: UUID,
    x_admin_key: str | None = Header(None, alias="X-Admin-Key"),
) -> AdminUserResponse:
    """Usuwa indywidualny limit — obowiązuje domyślny z konfiguracji (DEFAULT_USER_LLM_MONTHLY_COST_LIMIT_USD)."""
    _check_admin_key(x_admin_key)
    target = await session.get(UserORM, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Użytkownik nie znaleziony")
    target.llm_monthly_cost_limit_usd = None
    await session.commit()
    await session.refresh(target)
    return await _admin_user_response_with_usage(session, target)


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

    sum_cost = await session.scalar(select(func.coalesce(func.sum(LlmUsageLogORM.cost_usd), 0))) or 0

    by_model_rows = await session.execute(
        select(
            LlmUsageLogORM.model,
            LlmUsageLogORM.provider,
            func.count(LlmUsageLogORM.id).label("calls"),
            func.coalesce(func.sum(LlmUsageLogORM.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(LlmUsageLogORM.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(LlmUsageLogORM.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(LlmUsageLogORM.cost_usd), 0).label("cost_usd"),
        )
        .group_by(LlmUsageLogORM.model, LlmUsageLogORM.provider)
        .order_by(func.count(LlmUsageLogORM.id).desc())
    )
    by_model = [
        {
            "model": r.model, "provider": r.provider, "calls": int(r.calls),
            "prompt_tokens": int(r.prompt_tokens), "completion_tokens": int(r.completion_tokens),
            "total_tokens": int(r.total_tokens), "cost_usd": float(r.cost_usd or 0),
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
            func.coalesce(func.sum(LlmUsageLogORM.cost_usd), 0).label("cost_usd"),
        )
        .group_by(LlmUsageLogORM.call_kind, LlmUsageLogORM.module_name)
        .order_by(LlmUsageLogORM.call_kind, LlmUsageLogORM.module_name)
    )
    by_call_route = [
        {
            "call_kind": r.call_kind, "module_name": r.module_name, "calls": int(r.calls),
            "prompt_tokens": int(r.prompt_tokens), "completion_tokens": int(r.completion_tokens),
            "total_tokens": int(r.total_tokens), "cost_usd": float(r.cost_usd or 0),
        }
        for r in by_route_rows.all()
    ]

    langfuse_on = bool(s.langfuse_public_key and s.langfuse_secret_key)
    cost_month = await sum_llm_cost_usd_month(session, include_dry_run=False)
    limit_alerts = build_limit_alerts(cost_month)
    has_critical_limit = any(a.get("severity") == "critical" for a in limit_alerts)
    if has_critical_limit and s.alert_webhook_url:
        since = datetime.now(timezone.utc) - timedelta(minutes=15)
        sent = await count_recent_incidents(session, event_type="alert_webhook_llm_limit", since=since)
        if sent == 0:
            await record_system_incident(
                session, event_type="alert_webhook_llm_limit", severity="info",
                title="Wysłano webhook (przekroczenie limitu LLM)",
                detail={"alerts": limit_alerts, "cost_month_usd": cost_month},
            )
            await send_alert_webhook({"event": "llm_limit_critical", "severity": "critical", "cost_month_usd": cost_month, "alerts": limit_alerts})
            await session.commit()
    incidents = await list_recent_incidents(session, limit=40)
    per_user_costs = await per_user_llm_cost_stats(session)

    return {
        "application": {"users": users or 0, "files": files or 0, "ai_read_audits": audits or 0},
        "alerts": {
            "operational": limit_alerts, "cost_month_usd": cost_month,
            "soft_limit_usd": s.llm_monthly_cost_soft_limit_usd,
            "hard_limit_usd": s.llm_monthly_cost_hard_limit_usd,
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
            "total_cost_usd": float(sum_cost),
            "by_model": by_model, "by_call_kind_and_module": by_call_route,
            "description": (
                "Każde wywołanie modelu (LLM, obraz, embedding, muzyka…) jest zapisywane w llm_usage_log. "
                "Koszt USD pochodzi z odpowiedzi OpenRouter (usage.cost) lub szacunków konfiguracyjnych."
            ),
        },
        "langfuse": {
            "enabled": langfuse_on,
            "host": s.langfuse_host,
            "dashboard_url": s.langfuse_host.rstrip("/") + "/",
            "auth_ok": langfuse_auth_check_sync() if langfuse_on else False,
            "hint": (
                "Langfuse włączony — obserwacje w Tracing (environment: production); "
                "rozmowy w Sessions (session_id = conversation_id). Użyj „Test Langfuse”."
                if langfuse_on
                else "Uzupełnij LANGFUSE_* w .env, aby wysyłać obserwacje LLM do Langfuse Cloud."
            ),
        },
        "per_user_llm_costs": per_user_costs,
        "per_user_llm_costs_hint": (
            "Koszt USD bez dry-run. „Dziś” i „miesiąc” — kalendarz UTC. "
            "Limit / miesiąc: własny, domyślny (DEFAULT_USER_LLM_MONTHLY_COST_LIMIT_USD) lub brak (0 w bazie). "
            "Dotyczy wszystkich modeli na konto użytkownika."
        ),
    }


@router.post("/alerts/test-langfuse")
async def admin_test_langfuse(
    _session: DbSession,
    user: AdminUser,
    x_admin_key: str | None = Header(None, alias="X-Admin-Key"),
) -> dict:
    _check_admin_key(x_admin_key)
    s = get_settings()
    if not s.langfuse_public_key or not s.langfuse_secret_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Brak LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY")
    result = send_langfuse_test_event_sync()
    return {"host": s.langfuse_host, **result}


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
