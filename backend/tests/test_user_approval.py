from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from teacher_helper.adapters.http.deps import (
    ACCOUNT_PENDING_APPROVAL,
    initial_is_approved_for_email,
    require_approved_user,
)
from teacher_helper.adapters.http.routes_admin import _admin_user_response, assert_can_set_approval
from teacher_helper.infrastructure.db.models import UserORM, UserRole


def _user(*, email: str = "t@example.com", role: UserRole = UserRole.teacher, approved: bool = False) -> UserORM:
    return UserORM(
        id=uuid4(),
        email=email,
        hashed_password="x",
        role=role,
        is_approved=approved,
        created_at=datetime.now(timezone.utc),
    )


def test_allowlist_email_is_approved_on_insert(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    from teacher_helper.config import get_settings

    get_settings.cache_clear()
    assert initial_is_approved_for_email("admin@example.com") is True
    assert initial_is_approved_for_email("teacher@example.com") is False
    get_settings.cache_clear()


def test_require_approved_rejects_pending_user() -> None:
    with pytest.raises(HTTPException) as exc:
        require_approved_user(_user(approved=False))
    assert exc.value.status_code == 403
    assert exc.value.detail == ACCOUNT_PENDING_APPROVAL


def test_require_approved_allows_accepted_user() -> None:
    user = _user(approved=True)
    assert require_approved_user(user) is user


def test_admin_response_includes_is_approved() -> None:
    pending = _admin_user_response(_user(approved=False))
    assert pending.is_approved is False
    accepted = _admin_user_response(_user(approved=True))
    assert accepted.is_approved is True


def test_admin_cannot_revoke_self() -> None:
    admin = _user(email="admin@example.com", role=UserRole.admin, approved=True)
    with pytest.raises(HTTPException) as exc:
        assert_can_set_approval(admin, admin, False)
    assert exc.value.status_code == 403


def test_admin_can_accept_other_user() -> None:
    admin = _user(email="admin@example.com", role=UserRole.admin, approved=True)
    target = _user(email="new@example.com", approved=False)
    assert_can_set_approval(admin, target, True)


def _dep_names(path: str, method: str) -> set[str]:
    from teacher_helper.adapters.http import create_app

    names: set[str] = set()
    for route in create_app().routes:
        if getattr(route, "path", None) != path:
            continue
        methods = getattr(route, "methods", None) or set()
        if method not in methods:
            continue
        stack = [route.dependant]
        while stack:
            cur = stack.pop()
            if cur.call is not None:
                name = getattr(cur.call, "__name__", None)
                if isinstance(name, str):
                    names.add(name)
            stack.extend(cur.dependencies)
    return names


def test_chat_route_requires_approval() -> None:
    names = _dep_names("/v1/chat", "POST")
    assert "require_approved" in names


def test_me_route_does_not_require_approval() -> None:
    names = _dep_names("/v1/auth/me", "GET")
    assert "get_current_user" in names
    assert "require_approved" not in names
