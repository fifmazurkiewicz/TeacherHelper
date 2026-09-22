from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from teacher_helper.adapters.http.deps import CurrentUser, DbSession, initial_is_approved_for_email
from teacher_helper.adapters.http.schemas import MonthlyLlmUsageResponse, UserResponse
from teacher_helper.config import get_settings
from teacher_helper.infrastructure.usage_limits import (
    effective_user_llm_monthly_cost_limit_usd,
    sum_llm_cost_usd_month_for_user,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.get("/me", response_model=UserResponse)
async def me(session: DbSession, user: CurrentUser) -> UserResponse:
    await session.refresh(user)
    return UserResponse.model_validate(user)


@router.get("/usage", response_model=MonthlyLlmUsageResponse)
async def monthly_usage(session: DbSession, user: CurrentUser) -> MonthlyLlmUsageResponse:
    """Zwraca koszt AI od początku bieżącego miesiąca UTC i limit konta."""
    await session.refresh(user)
    cost_month_usd = await sum_llm_cost_usd_month_for_user(session, user.id)
    limit_usd = effective_user_llm_monthly_cost_limit_usd(user)
    return MonthlyLlmUsageResponse(
        llm_cost_month_usd=cost_month_usd,
        effective_llm_monthly_cost_limit_usd=limit_usd,
        llm_monthly_limit_reached=limit_usd is not None and cost_month_usd >= limit_usd,
    )


def _legacy_auth_enabled() -> bool:
    return not get_settings().supabase_url


if _legacy_auth_enabled():
    from uuid import uuid4

    from sqlalchemy import select

    from teacher_helper.adapters.http.schemas import LoginRequest, RegisterRequest, TokenResponse
    from teacher_helper.infrastructure.db.models import UserORM, UserRole
    from teacher_helper.security import create_access_token, hash_password, verify_password

    @router.post("/register", response_model=TokenResponse)
    async def register(session: DbSession, body: RegisterRequest) -> TokenResponse:
        existing = await session.scalar(select(UserORM).where(UserORM.email == body.email.lower()))
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="E-mail jest już zarejestrowany")
        user = UserORM(
            id=uuid4(),
            email=body.email.lower(),
            hashed_password=hash_password(body.password),
            role=UserRole.teacher,
            display_name=body.display_name,
            is_approved=initial_is_approved_for_email(body.email),
        )
        session.add(user)
        await session.commit()
        token = create_access_token(user.id)
        return TokenResponse(access_token=token)

    @router.post("/login", response_model=TokenResponse)
    async def login(session: DbSession, body: LoginRequest) -> TokenResponse:
        user = await session.scalar(select(UserORM).where(UserORM.email == body.email.lower()))
        if not user or not user.hashed_password or not verify_password(body.password, user.hashed_password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Błędny e-mail lub hasło")
        token = create_access_token(user.id)
        return TokenResponse(access_token=token)
