from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from jose import JWTError, jwt

from teacher_helper.config import get_settings

CONFIRM_TYP = "resource_confirm"

ACTION_DELETE_FILE = "delete_file"
ACTION_REINDEX_FILE = "reindex_file"
ACTION_DELETE_PROJECT = "delete_project"
ACTION_CREATE_PROJECT = "create_project"

RESOURCE_FILE = "file"
RESOURCE_PROJECT = "project"


def create_resource_confirmation_token(
    *,
    user_id: UUID,
    action: str,
    resource_type: str,
    resource_id: UUID,
) -> str:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.confirmation_token_expire_minutes)
    payload = {
        "typ": CONFIRM_TYP,
        "sub": str(user_id),
        "act": action,
        "rty": resource_type,
        "rid": str(resource_id),
        "exp": exp,
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def verify_resource_confirmation_token(
    token: str,
    *,
    user_id: UUID,
    action: str,
    resource_type: str,
    resource_id: UUID,
) -> bool:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
        if payload.get("typ") != CONFIRM_TYP:
            return False
        if payload.get("sub") != str(user_id):
            return False
        if payload.get("act") != action:
            return False
        if payload.get("rty") != resource_type:
            return False
        if payload.get("rid") != str(resource_id):
            return False
        return True
    except JWTError:
        return False


def create_project_creation_token(
    *,
    user_id: UUID,
    name: str,
    description: str | None,
) -> str:
    """Token na utworzenie projektu — nazwa i opis zapisane w JWT (krótkie, by nie przekroczyć nagłówka)."""
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.confirmation_token_expire_minutes)
    payload: dict[str, Any] = {
        "typ": CONFIRM_TYP,
        "sub": str(user_id),
        "act": ACTION_CREATE_PROJECT,
        "rty": RESOURCE_PROJECT,
        "rid": str(uuid4()),
        "pn": (name or "")[:220],
        "pd": ((description or "")[:1800]),
        "exp": exp,
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def verify_project_creation_token(token: str, *, user_id: UUID) -> tuple[bool, str, str | None]:
    """Zwraca (ok, name, description) z tokena utworzenia projektu."""
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
        if payload.get("typ") != CONFIRM_TYP:
            return False, "", None
        if payload.get("sub") != str(user_id):
            return False, "", None
        if payload.get("act") != ACTION_CREATE_PROJECT:
            return False, "", None
        if payload.get("rty") != RESOURCE_PROJECT:
            return False, "", None
        name = str(payload.get("pn") or "").strip()
        if not name:
            return False, "", None
        desc_raw = payload.get("pd")
        desc = str(desc_raw).strip() if desc_raw not in (None, "") else None
        return True, name, desc
    except JWTError:
        return False, "", None
