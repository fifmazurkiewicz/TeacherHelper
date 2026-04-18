from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_helper.config import get_settings
from teacher_helper.infrastructure.db.models import LlmUsageLogORM


def utc_day_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def sum_llm_total_tokens_today(session: AsyncSession, *, include_dry_run: bool = False) -> int:
    start = utc_day_start()
    stmt = select(func.coalesce(func.sum(LlmUsageLogORM.total_tokens), 0)).where(
        LlmUsageLogORM.created_at >= start,
    )
    if not include_dry_run:
        stmt = stmt.where(LlmUsageLogORM.dry_run.is_(False))
    val = await session.scalar(stmt)
    return int(val or 0)


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
