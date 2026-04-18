from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from teacher_helper.infrastructure.db.models import UserORM, UserRole
from teacher_helper.infrastructure.db.session import async_session_factory
from teacher_helper.security import decode_user_id

security = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    session: DbSession,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> UserORM:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Wymagany nagłówek Authorization: Bearer")
    uid = decode_user_id(creds.credentials)
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
