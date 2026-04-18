from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import func, select

from teacher_helper.adapters.http.deps import CurrentUser, DbSession
from teacher_helper.adapters.http.schemas import ProjectCreate, ProjectResponse
from teacher_helper.config import get_settings
from teacher_helper.infrastructure.db.models import FileAssetORM, ProjectORM
from teacher_helper.security.resource_confirmation import (
    ACTION_DELETE_PROJECT,
    RESOURCE_PROJECT,
    create_project_creation_token,
    create_resource_confirmation_token,
    verify_project_creation_token,
    verify_resource_confirmation_token,
)

router = APIRouter(prefix="/v1/projects", tags=["projects"])


@router.post("/prepare-create")
async def project_prepare_create(session: DbSession, user: CurrentUser, body: ProjectCreate) -> dict:
    """Zwraca token — utworzenie projektu wymaga nagłówka ``X-Resource-Confirmation`` (gdy włączone w konfiguracji)."""
    s = get_settings()
    token = create_project_creation_token(
        user_id=user.id,
        name=body.name.strip(),
        description=body.description.strip() if body.description else None,
    )
    return {
        "confirmation_token": token,
        "expires_in_seconds": s.confirmation_token_expire_minutes * 60,
        "header_name": "X-Resource-Confirmation",
        "summary": f"Czy utworzyć projekt „{body.name.strip()}”?",
    }


@router.post("", response_model=ProjectResponse)
async def create_project(
    session: DbSession,
    user: CurrentUser,
    body: ProjectCreate | None = None,
    x_resource_confirmation: str | None = Header(default=None, alias="X-Resource-Confirmation"),
) -> ProjectORM:
    s = get_settings()
    if s.require_resource_confirmation:
        tok = (x_resource_confirmation or "").strip()
        if not tok:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "code": "CONFIRMATION_REQUIRED",
                    "message": "Najpierw POST /v1/projects/prepare-create z {name, description}, potem POST /v1/projects z nagłówkiem X-Resource-Confirmation.",
                },
            )
        ok, name, desc = verify_project_creation_token(tok, user_id=user.id)
        if not ok:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Nieprawidłowy lub wygasły token potwierdzenia utworzenia projektu.",
            )
        p = ProjectORM(id=uuid4(), user_id=user.id, name=name, description=desc)
        session.add(p)
        await session.commit()
        await session.refresh(p)
        return p
    if body is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Brak treści żądania (name).")
    p = ProjectORM(id=uuid4(), user_id=user.id, name=body.name, description=body.description)
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return p


@router.get("", response_model=list[ProjectResponse])
async def list_projects(session: DbSession, user: CurrentUser) -> list[ProjectORM]:
    stmt = select(ProjectORM).where(ProjectORM.user_id == user.id).order_by(ProjectORM.created_at.desc())
    rows = (await session.scalars(stmt)).all()
    return list(rows)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(session: DbSession, user: CurrentUser, project_id: UUID) -> ProjectORM:
    p = await session.get(ProjectORM, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Projekt nie znaleziony")
    return p


@router.get("/{project_id}/delete-impact")
async def project_delete_impact(session: DbSession, user: CurrentUser, project_id: UUID) -> dict:
    p = await session.get(ProjectORM, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Projekt nie znaleziony")
    n_files = await session.scalar(
        select(func.count()).select_from(FileAssetORM).where(FileAssetORM.project_id == project_id)
    )
    return {
        "resource": "project",
        "project_id": str(project_id),
        "name": p.name,
        "files_attached_count": int(n_files or 0),
        "message": "Usunięcie projektu nie usuwa plików — powiązanie project_id w plikach zostanie skasowane (SET NULL).",
    }


@router.post("/{project_id}/prepare-delete")
async def project_prepare_delete(session: DbSession, user: CurrentUser, project_id: UUID) -> dict:
    p = await session.get(ProjectORM, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Projekt nie znaleziony")
    s = get_settings()
    token = create_resource_confirmation_token(
        user_id=user.id,
        action=ACTION_DELETE_PROJECT,
        resource_type=RESOURCE_PROJECT,
        resource_id=project_id,
    )
    return {
        "confirmation_token": token,
        "expires_in_seconds": s.confirmation_token_expire_minutes * 60,
        "header_name": "X-Resource-Confirmation",
        "summary": f"Czy na pewno usunąć projekt „{p.name}”? Pliki pozostaną w bibliotece bez przypisania do tego projektu.",
    }


@router.delete("/{project_id}", response_model=None)
async def delete_project(
    session: DbSession,
    user: CurrentUser,
    project_id: UUID,
    dry_run: bool = False,
    x_resource_confirmation: str | None = Header(None, alias="X-Resource-Confirmation"),
) -> Response | dict:
    p = await session.get(ProjectORM, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Projekt nie znaleziony")
    s = get_settings()
    if dry_run:
        n_files = await session.scalar(
            select(func.count()).select_from(FileAssetORM).where(FileAssetORM.project_id == project_id)
        )
        return {
            "dry_run": True,
            "would_delete": True,
            "project_id": str(project_id),
            "name": p.name,
            "files_losing_project_link": int(n_files or 0),
        }
    if s.require_resource_confirmation:
        tok = x_resource_confirmation or ""
        if not verify_resource_confirmation_token(
            tok,
            user_id=user.id,
            action=ACTION_DELETE_PROJECT,
            resource_type=RESOURCE_PROJECT,
            resource_id=project_id,
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "code": "CONFIRMATION_REQUIRED",
                    "message": "Potwierdź usunięcie — POST /v1/projects/{id}/prepare-delete, potem DELETE z nagłówkiem X-Resource-Confirmation.",
                },
            )
    await session.delete(p)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
