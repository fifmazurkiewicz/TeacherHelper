from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from teacher_helper.adapters.http.routes_admin import _admin_user_response
from teacher_helper.infrastructure.db.models import UserORM, UserRole


def _user(limit: Decimal | None) -> UserORM:
    u = UserORM(
        id=uuid4(),
        email="t@example.com",
        hashed_password="x",
        role=UserRole.teacher,
        is_approved=True,
        created_at=datetime.now(timezone.utc),
    )
    u.llm_monthly_cost_limit_usd = limit
    return u


def test_admin_user_response_usage_and_limit_reached(monkeypatch) -> None:
    monkeypatch.setenv("DEFAULT_USER_LLM_MONTHLY_COST_LIMIT_USD", "10")
    get_settings = __import__("teacher_helper.config", fromlist=["get_settings"]).get_settings
    get_settings.cache_clear()

    resp = _admin_user_response(_user(None), llm_cost_month_usd=10.0, llm_tokens_month=42_000)
    assert resp.llm_cost_month_usd == 10.0
    assert resp.llm_tokens_month == 42_000
    assert resp.effective_llm_monthly_cost_limit_usd == 10.0
    assert resp.llm_monthly_limit_reached is True

    resp_ok = _admin_user_response(_user(None), llm_cost_month_usd=9.99, llm_tokens_month=1)
    assert resp_ok.llm_monthly_limit_reached is False

    resp_unlimited = _admin_user_response(_user(Decimal("0")), llm_cost_month_usd=100.0, llm_tokens_month=1)
    assert resp_unlimited.effective_llm_monthly_cost_limit_usd is None
    assert resp_unlimited.llm_monthly_limit_reached is False


def test_admin_user_response_custom_limit() -> None:
    resp = _admin_user_response(_user(Decimal("5")), llm_cost_month_usd=5.0, llm_tokens_month=0)
    assert resp.effective_llm_monthly_cost_limit_usd == 5.0
    assert resp.llm_monthly_limit_reached is True
    assert resp.uses_site_default_llm_monthly_limit is False
