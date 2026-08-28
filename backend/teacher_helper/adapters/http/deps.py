from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_helper.config import get_settings
from teacher_helper.infrastructure.db.models import UserORM, UserRole
from teacher_helper.infrastructure.db.session import async_session_factory
from teacher_helper.security import decode_user_id
from teacher_helper.security.supabase_jwt import extract_user_id_from_payload, verify_supabase_access_token

security = HTTPBearer(auto_error=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def _ensure_user_profile(session: AsyncSession, user_id: UUID, email: str | None) -> UserORM:
    user = await session.get(UserORM, user_id)
    if user is not None:
        return user
    if not email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Brak e-mail w tokenie — nie można utworzyć profilu")
    user = UserORM(
        id=user_id,
        email=email.lower(),
        hashed_password=None,
        role=UserRole.teacher,
    )
    session.add(user)
    await session.flush()
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


async def require_admin(user: CurrentUser) -> UserORM:
    if user.role != UserRole.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Wymagana rola administratora")
    return user


AdminUser = Annotated[UserORM, Depends(require_admin)]
