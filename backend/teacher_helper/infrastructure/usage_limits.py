from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_helper.config import Settings, get_settings
from teacher_helper.infrastructure.db.models import LlmUsageLogORM, UserORM


def utc_day_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def utc_month_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _cost_sum_expr():
    return func.coalesce(LlmUsageLogORM.cost_usd, 0)


async def sum_llm_cost_usd_today(session: AsyncSession, *, include_dry_run: bool = False) -> float:
    start = utc_day_start()
    stmt = select(func.coalesce(func.sum(_cost_sum_expr()), 0)).where(
        LlmUsageLogORM.created_at >= start,
    )
    if not include_dry_run:
        stmt = stmt.where(LlmUsageLogORM.dry_run.is_(False))
    val = await session.scalar(stmt)
    return float(val or 0)


async def sum_llm_cost_usd_month(session: AsyncSession, *, include_dry_run: bool = False) -> float:
    start = utc_month_start()
    stmt = select(func.coalesce(func.sum(_cost_sum_expr()), 0)).where(
        LlmUsageLogORM.created_at >= start,
    )
    if not include_dry_run:
        stmt = stmt.where(LlmUsageLogORM.dry_run.is_(False))
    val = await session.scalar(stmt)
    return float(val or 0)


def effective_user_llm_monthly_cost_limit_usd(user: UserORM, settings: Settings | None = None) -> float | None:
    """Limit kosztu LLM / miesiąc kalendarzowy (UTC) w USD."""
    s = settings or get_settings()
    raw = user.llm_monthly_cost_limit_usd
    if raw is None:
        return float(s.default_user_llm_monthly_cost_limit_usd)
    if raw == 0:
        return None
    return float(raw)


async def sum_llm_cost_usd_month_for_user(
    session: AsyncSession,
    user_id: UUID,
    *,
    include_dry_run: bool = False,
) -> float:
    start = utc_month_start()
    stmt = (
        select(func.coalesce(func.sum(_cost_sum_expr()), 0))
        .where(LlmUsageLogORM.user_id == user_id)
        .where(LlmUsageLogORM.created_at >= start)
    )
    if not include_dry_run:
        stmt = stmt.where(LlmUsageLogORM.dry_run.is_(False))
    val = await session.scalar(stmt)
    return float(val or 0)


async def llm_usage_month_by_user_id(
    session: AsyncSession,
    *,
    include_dry_run: bool = False,
) -> dict[UUID, dict[str, float | int]]:
    """Bieżący miesiąc kalendarzowy UTC: koszt USD i suma tokenów per user_id (bez dry-run domyślnie)."""
    month_start = utc_month_start()
    cost = _cost_sum_expr()
    tok = func.coalesce(LlmUsageLogORM.total_tokens, 0)
    stmt = (
        select(
            LlmUsageLogORM.user_id.label("uid"),
            func.coalesce(func.sum(cost), 0).label("cost_month_usd"),
            func.coalesce(func.sum(tok), 0).label("tokens_month"),
        )
        .where(LlmUsageLogORM.user_id.isnot(None))
        .where(LlmUsageLogORM.created_at >= month_start)
    )
    if not include_dry_run:
        stmt = stmt.where(LlmUsageLogORM.dry_run.is_(False))
    stmt = stmt.group_by(LlmUsageLogORM.user_id)
    rows = (await session.execute(stmt)).all()
    return {
        r.uid: {
            "cost_month_usd": float(r.cost_month_usd or 0),
            "tokens_month": int(r.tokens_month or 0),
        }
        for r in rows
    }


async def user_llm_usage_month(
    session: AsyncSession,
    user_id: UUID,
    *,
    include_dry_run: bool = False,
) -> dict[str, float | int]:
    """Bieżący miesiąc UTC dla jednego użytkownika."""
    month_start = utc_month_start()
    cost = _cost_sum_expr()
    tok = func.coalesce(LlmUsageLogORM.total_tokens, 0)
    stmt = (
        select(
            func.coalesce(func.sum(cost), 0).label("cost_month_usd"),
            func.coalesce(func.sum(tok), 0).label("tokens_month"),
        )
        .where(LlmUsageLogORM.user_id == user_id)
        .where(LlmUsageLogORM.created_at >= month_start)
    )
    if not include_dry_run:
        stmt = stmt.where(LlmUsageLogORM.dry_run.is_(False))
    row = (await session.execute(stmt)).one()
    return {
        "cost_month_usd": float(row.cost_month_usd or 0),
        "tokens_month": int(row.tokens_month or 0),
    }


async def per_user_llm_cost_stats(session: AsyncSession) -> list[dict[str, Any]]:
    """Dla każdego konta: koszt USD dzień / miesiąc (UTC) / cały czas (bez dry-run)."""
    s = get_settings()
    day_start = utc_day_start()
    month_start = utc_month_start()
    cost = _cost_sum_expr()
    tok = func.coalesce(LlmUsageLogORM.total_tokens, 0)

    sub = (
        select(
            LlmUsageLogORM.user_id.label("uid"),
            func.coalesce(
                func.sum(case((LlmUsageLogORM.created_at >= day_start, cost), else_=0)),
                0,
            ).label("cost_today_usd"),
            func.coalesce(
                func.sum(case((LlmUsageLogORM.created_at >= month_start, cost), else_=0)),
                0,
            ).label("cost_month_usd"),
            func.coalesce(func.sum(cost), 0).label("cost_all_usd"),
            func.coalesce(
                func.sum(case((LlmUsageLogORM.created_at >= day_start, tok), else_=0)),
                0,
            ).label("tokens_today"),
            func.coalesce(
                func.sum(case((LlmUsageLogORM.created_at >= month_start, tok), else_=0)),
                0,
            ).label("tokens_month"),
            func.coalesce(func.sum(tok), 0).label("tokens_all"),
        )
        .where(LlmUsageLogORM.user_id.isnot(None))
        .where(LlmUsageLogORM.dry_run.is_(False))
        .group_by(LlmUsageLogORM.user_id)
    ).subquery()

    stmt = (
        select(
            UserORM.id,
            UserORM.email,
            UserORM.llm_monthly_cost_limit_usd,
            sub.c.cost_today_usd,
            sub.c.cost_month_usd,
            sub.c.cost_all_usd,
            sub.c.tokens_today,
            sub.c.tokens_month,
            sub.c.tokens_all,
        )
        .outerjoin(sub, UserORM.id == sub.c.uid)
        .order_by(UserORM.email.asc())
    )
    rows = (await session.execute(stmt)).all()
    out: list[dict[str, Any]] = []
    for r in rows:
        raw = r.llm_monthly_cost_limit_usd
        if raw is None:
            eff: float | None = float(s.default_user_llm_monthly_cost_limit_usd)
            uses_default = True
        elif raw == 0:
            eff = None
            uses_default = False
        else:
            eff = float(raw)
            uses_default = False
        out.append(
            {
                "user_id": str(r.id),
                "email": r.email,
                "cost_today_usd": float(r.cost_today_usd or 0),
                "cost_month_usd": float(r.cost_month_usd or 0),
                "cost_all_time_usd": float(r.cost_all_usd or 0),
                "tokens_today_utc": int(r.tokens_today or 0),
                "tokens_month_utc": int(r.tokens_month or 0),
                "tokens_all_time": int(r.tokens_all or 0),
                "llm_monthly_cost_limit_usd": float(raw) if raw is not None else None,
                "effective_llm_monthly_cost_limit_usd": eff,
                "uses_site_default_llm_monthly_limit": uses_default,
            }
        )
    return out


def build_limit_alerts(cost_month_usd: float) -> list[dict]:
    s = get_settings()
    alerts: list[dict] = []
    hard = s.llm_monthly_cost_hard_limit_usd
    soft = s.llm_monthly_cost_soft_limit_usd
    if hard is not None and cost_month_usd >= hard:
        alerts.append(
            {
                "code": "LLM_MONTHLY_COST_HARD",
                "severity": "critical",
                "message": (
                    f"Przekroczono twardy miesięczny limit kosztu LLM: ${cost_month_usd:.4f} ≥ ${hard:.2f}."
                ),
                "cost_month_usd": cost_month_usd,
                "hard_limit_usd": hard,
            }
        )
    elif soft is not None and cost_month_usd >= soft:
        alerts.append(
            {
                "code": "LLM_MONTHLY_COST_SOFT",
                "severity": "warning",
                "message": (
                    f"Zużycie kosztu LLM (miesiąc UTC, bez dry-run): ${cost_month_usd:.4f} ≥ limit miękki "
                    f"${soft:.2f}."
                ),
                "cost_month_usd": cost_month_usd,
                "soft_limit_usd": soft,
            }
        )
    return alerts


async def assert_user_within_monthly_cost_limit(
    session: AsyncSession,
    user: UserORM,
    settings: Settings | None = None,
) -> None:
    """Sprawdza globalny i per-użytkownik limit kosztu LLM (miesiąc UTC). Rzuca HTTP 429 przy przekroczeniu."""
    s = settings or get_settings()
    cost_month = await sum_llm_cost_usd_month(session, include_dry_run=False)
    if s.llm_monthly_cost_hard_limit_usd is not None and cost_month >= s.llm_monthly_cost_hard_limit_usd:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Miesięczny limit kosztu LLM (cała aplikacja) został wyczerpany. "
                "Spróbuj w kolejnym miesiącu (UTC) lub skontaktuj się z administratorem."
            ),
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
