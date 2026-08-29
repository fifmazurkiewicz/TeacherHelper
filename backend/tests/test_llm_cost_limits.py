from __future__ import annotations

from decimal import Decimal

import pytest

from teacher_helper.config import Settings
from teacher_helper.infrastructure.db.models import UserORM, UserRole
from teacher_helper.infrastructure.usage_limits import effective_user_llm_monthly_cost_limit_usd


def _user(limit: Decimal | None) -> UserORM:
    u = UserORM(email="t@example.com", hashed_password="x", role=UserRole.teacher)
    u.llm_monthly_cost_limit_usd = limit
    return u


def test_effective_limit_default() -> None:
    s = Settings(default_user_llm_monthly_cost_limit_usd=10.0)
    assert effective_user_llm_monthly_cost_limit_usd(_user(None), s) == 10.0


def test_effective_limit_custom() -> None:
    s = Settings(default_user_llm_monthly_cost_limit_usd=10.0)
    assert effective_user_llm_monthly_cost_limit_usd(_user(Decimal("25.50")), s) == 25.5


def test_effective_limit_zero_means_unlimited_per_user() -> None:
    s = Settings(default_user_llm_monthly_cost_limit_usd=10.0)
    assert effective_user_llm_monthly_cost_limit_usd(_user(Decimal("0")), s) is None


def test_cost_from_openrouter_response() -> None:
    from teacher_helper.infrastructure.db.llm_usage import cost_from_openrouter_response

    assert cost_from_openrouter_response({"usage": {"cost": 0.0123}}) == pytest.approx(0.0123)
    assert cost_from_openrouter_response({"usage": {}}) is None
