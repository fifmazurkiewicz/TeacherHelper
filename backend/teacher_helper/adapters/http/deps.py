from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_helper.config import get_settings, parse_admin_emails
from teacher_helper.infrastructure.db.models import UserORM, UserRole
from teacher_helper.infrastructure.db.session import async_session_factory
from teacher_helper.security import decode_user_id
from teacher_helper.security.supabase_jwt import extract_user_id_from_payload, verify_supabase_access_token

security = HTTPBearer(auto_error=False)

ACCOUNT_PENDING_APPROVAL = {
    "code": "account_pending_approval",
    "message": "Konto oczekuje na akceptację administratora.",
}


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def _resolve_role_for_email(email: str) -> UserRole:
    allowed = parse_admin_emails(get_settings().admin_emails)
    if not allowed:
        return UserRole.teacher
    return UserRole.admin if email.strip().lower() in allowed else UserRole.teacher


def initial_is_approved_for_email(email: str) -> bool:
    allowed = parse_admin_emails(get_settings().admin_emails)
    if not allowed:
        return False
    return email.strip().lower() in allowed


def require_approved_user(user: UserORM) -> UserORM:
    if not user.is_approved:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=ACCOUNT_PENDING_APPROVAL)
    return user


def _apply_admin_email_policy(user: UserORM, email: str) -> None:
    allowed = parse_admin_emails(get_settings().admin_emails)
    if not allowed:
        return
    normalized = email.strip().lower()
    if normalized in allowed:
        user.role = UserRole.admin
    elif user.role == UserRole.admin:
        user.role = UserRole.teacher


async def _ensure_user_profile(session: AsyncSession, user_id: UUID, email: str | None) -> UserORM:
    user = await session.get(UserORM, user_id)
    if user is not None:
        if email:
            _apply_admin_email_policy(user, email)
        return user
    if not email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Brak e-mail w tokenie — nie można utworzyć profilu")
    user = UserORM(
        id=user_id,
        email=email.lower(),
        hashed_password=None,
        role=_resolve_role_for_email(email),
        is_approved=initial_is_approved_for_email(email),
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        user = await session.get(UserORM, user_id)
        if user is None:
            raise
        if email:
            _apply_admin_email_policy(user, email)
        return user
    return user


async def get_current_user(
    session: DbSession,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> UserORM:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Wymagany nagłówek Authorization: Bearer")

    token = creds.credentials
    s = get_settings()

    if s.supabase_url:
        payload = await verify_supabase_access_token(token)
        if payload is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowy token Supabase")
        uid = extract_user_id_from_payload(payload)
        email = payload.get("email")
        if isinstance(email, str):
            user = await _ensure_user_profile(session, uid, email)
        else:
            user = await session.get(UserORM, uid)
            if user is None:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Profil użytkownika nie istnieje")
        await session.commit()
        return user

    uid = decode_user_id(token)
    if uid is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowy token")
    user = await session.get(UserORM, uid)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Użytkownik nie istnieje")
    return user


CurrentUser = Annotated[UserORM, Depends(get_current_user)]


async def require_approved(user: CurrentUser) -> UserORM:
    return require_approved_user(user)


ApprovedUser = Annotated[UserORM, Depends(require_approved)]


async def require_admin(user: ApprovedUser) -> UserORM:
    if user.role != UserRole.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Wymagana rola administratora")
    return user


AdminUser = Annotated[UserORM, Depends(require_admin)]
