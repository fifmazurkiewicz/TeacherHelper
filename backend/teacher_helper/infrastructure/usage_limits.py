from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

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


async def sum_llm_total_tokens_today(session: AsyncSession, *, include_dry_run: bool = False) -> int:
    start = utc_day_start()
    stmt = select(func.coalesce(func.sum(LlmUsageLogORM.total_tokens), 0)).where(
        LlmUsageLogORM.created_at >= start,
    )
    if not include_dry_run:
        stmt = stmt.where(LlmUsageLogORM.dry_run.is_(False))
    val = await session.scalar(stmt)
    return int(val or 0)


def effective_user_llm_daily_token_limit(user: UserORM, settings: Settings | None = None) -> int | None:
    """Limit tokenów LLM / dobę (UTC) dla czatu: wartość z konta, domyślna z konfiguracji, albo None = brak limitu per konto (tylko globalne limity)."""
    s = settings or get_settings()
    raw = user.llm_daily_token_limit
    if raw is None:
        return int(s.default_user_llm_daily_token_limit)
    if raw == 0:
        return None
    return int(raw)


async def sum_llm_total_tokens_today_for_user(
    session: AsyncSession,
    user_id: UUID,
    *,
    include_dry_run: bool = False,
) -> int:
    start = utc_day_start()
    tok = func.coalesce(LlmUsageLogORM.total_tokens, 0)
    stmt = (
        select(func.coalesce(func.sum(tok), 0))
        .where(LlmUsageLogORM.user_id == user_id)
        .where(LlmUsageLogORM.created_at >= start)
    )
    if not include_dry_run:
        stmt = stmt.where(LlmUsageLogORM.dry_run.is_(False))
    val = await session.scalar(stmt)
    return int(val or 0)


async def per_user_llm_token_stats(session: AsyncSession) -> list[dict[str, Any]]:
    """Dla każdego konta: suma tokenów dzień / miesiąc kalendarzowy (UTC) / cały czas (bez dry-run)."""
    s = get_settings()
    day_start = utc_day_start()
    month_start = utc_month_start()
    tok = func.coalesce(LlmUsageLogORM.total_tokens, 0)

    sub = (
        select(
            LlmUsageLogORM.user_id.label("uid"),
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
            UserORM.llm_daily_token_limit,
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
        raw = r.llm_daily_token_limit
        if raw is None:
            eff: int | None = int(s.default_user_llm_daily_token_limit)
            uses_default = True
        elif raw == 0:
            eff = None
            uses_default = False
        else:
            eff = int(raw)
            uses_default = False
        out.append(
            {
                "user_id": str(r.id),
                "email": r.email,
                "tokens_today_utc": int(r.tokens_today or 0),
                "tokens_month_utc": int(r.tokens_month or 0),
                "tokens_all_time": int(r.tokens_all or 0),
                "llm_daily_token_limit": raw,
                "effective_llm_daily_token_limit": eff,
                "uses_site_default_llm_daily_limit": uses_default,
            }
        )
    return out


def build_limit_alerts(tokens_today: int) -> list[dict]:
    s = get_settings()
    alerts: list[dict] = []
    if s.llm_daily_token_hard_limit is not None and tokens_today >= s.llm_daily_token_hard_limit:
        alerts.append(
            {
                "code": "LLM_DAILY_TOKENS_HARD",
                "severity": "critical",
                "message": (
                    f"Przekroczono twardy limit dzienny tokenów LLM: {tokens_today} ≥ {s.llm_daily_token_hard_limit}."
                ),
                "tokens_today": tokens_today,
                "hard_limit": s.llm_daily_token_hard_limit,
            }
        )
    elif s.llm_daily_token_soft_limit is not None and tokens_today >= s.llm_daily_token_soft_limit:
        alerts.append(
            {
                "code": "LLM_DAILY_TOKENS_SOFT",
                "severity": "warning",
                "message": (
                    f"Zużycie tokenów LLM (dzisiaj UTC, bez dry-run): {tokens_today} ≥ limit miękki "
                    f"{s.llm_daily_token_soft_limit}."
                ),
                "tokens_today": tokens_today,
                "soft_limit": s.llm_daily_token_soft_limit,
            }
        )
    return alerts
