from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from teacher_helper.adapters.http import routes_admin


def test_admin_key_not_required_when_request_has_no_header(monkeypatch) -> None:
    monkeypatch.setattr(
        routes_admin,
        "get_settings",
        lambda: SimpleNamespace(admin_api_key="server-secret"),
    )
    routes_admin._check_admin_key(None)
    routes_admin._check_admin_key("")
    routes_admin._check_admin_key("   ")


def test_wrong_admin_key_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        routes_admin,
        "get_settings",
        lambda: SimpleNamespace(admin_api_key="server-secret"),
    )
    with pytest.raises(HTTPException) as exc:
        routes_admin._check_admin_key("wrong")
    assert exc.value.status_code == 403
    routes_admin._check_admin_key("server-secret")


def test_admin_key_unset_allows_jwt_only(monkeypatch) -> None:
    monkeypatch.setattr(
        routes_admin,
        "get_settings",
        lambda: SimpleNamespace(admin_api_key=None),
    )
    routes_admin._check_admin_key(None)
    routes_admin._check_admin_key("anything")
