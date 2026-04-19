from __future__ import annotations

import io
import re
import zipfile
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import func, select

from teacher_helper.adapters.http.deps import CurrentUser, DbSession
from teacher_helper.adapters.http.rate_limit import check_rate_limit
from teacher_helper.adapters.http.schemas import ProjectCreate, ProjectResponse
from teacher_helper.config import get_settings
from teacher_helper.infrastructure.db.file_ops import purge_file_asset
from teacher_helper.infrastructure.db.models import FileAssetORM, ProjectORM
from teacher_helper.infrastructure.storage.local import LocalStorage
from teacher_helper.security.resource_confirmation import (
    ACTION_DELETE_PROJECT,
    RESOURCE_PROJECT,
    create_project_creation_token,
    create_resource_confirmation_token,
    verify_project_creation_token,
    verify_resource_confirmation_token,
)

router = APIRouter(prefix="/v1/projects", tags=["projects"])

# Limit archiwum ZIP (suma rozmiarów plików w katalogu) — unika OOM przy wielu dużych plikach.
_MAX_PROJECT_ARCHIVE_TOTAL_BYTES = 150 * 1024 * 1024


def _content_disposition_attachment(filename: str) -> str:
    enc = quote(filename, safe="")
    fallback = filename.encode("ascii", "replace").decode("ascii").replace("?", "_")
    fallback = "".join(c for c in fallback if c not in '"\\')[:200]
    if not fallback.strip(" ."):
        fallback = "download"
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{enc}"


def _safe_archive_folder_name(name: str) -> str:
    s = (name or "").strip() or "katalog"
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s)
    s = re.sub(r"\s+", "_", s).strip(" ._") or "katalog"
    return s[:120]


def _unique_zip_entry_name(filename: str, seen: dict[str, int]) -> str:
    base = (filename or "plik.bin").strip()
    base = base.replace("\\", "_").replace("/", "_") or "plik.bin"
    cnt = seen.get(base, 0)
    if cnt == 0:
        seen[base] = 1
        return base
    seen[base] = cnt + 1
    n = cnt
    if "." in base:
        stem, ext = base.rsplit(".", 1)
        return f"{stem} ({n}).{ext}"
    return f"{base} ({n})"


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


@router.get("/{project_id}/download-archive")
async def download_project_archive(
    session: DbSession,
    user: CurrentUser,
    project_id: UUID,
) -> Response:
    """Pobiera wszystkie pliki katalogu jako jedno archiwum ZIP (płaska struktura w podfolderze nazwanego jak projekt)."""
    check_rate_limit(user)
    p = await session.get(ProjectORM, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Projekt nie znaleziony")
    stmt = (
        select(FileAssetORM)
        .where(
            FileAssetORM.user_id == user.id,
            FileAssetORM.project_id == project_id,
        )
        .order_by(FileAssetORM.created_at.asc())
    )
    file_rows = list((await session.scalars(stmt)).all())
    if not file_rows:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="W tym katalogu nie ma plików do pobrania.",
        )
    total = sum(int(r.size_bytes or 0) for r in file_rows)
    if total > _MAX_PROJECT_ARCHIVE_TOTAL_BYTES:
        lim_mb = _MAX_PROJECT_ARCHIVE_TOTAL_BYTES // (1024 * 1024)
        total_mb = total // (1024 * 1024)
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"\u0141\u0105czny rozmiar plik\u00f3w ({total_mb} MB) przekracza limit archiwum "
                f"({lim_mb} MB). Pobierz wybrane pliki pojedynczo."
            ),
        )
    storage = LocalStorage()
    buf = io.BytesIO()
    folder = _safe_archive_folder_name(p.name)
    seen_names: dict[str, int] = {}
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for row in file_rows:
            data = await storage.get(row.storage_key)
            arc = f"{folder}/{_unique_zip_entry_name(row.name, seen_names)}"
            zf.writestr(arc, data)
    buf.seek(0)
    zip_bytes = buf.getvalue()
    zip_filename = f"{folder}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition_attachment(zip_filename)},
    )


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
        "message": "Usunięcie projektu trwale usuwa także wszystkie pliki przypisane do tego folderu (storage i indeks wyszukiwania).",
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
    n_files = await session.scalar(
        select(func.count()).select_from(FileAssetORM).where(FileAssetORM.project_id == project_id)
    )
    nf = int(n_files or 0)
    files_note = (
        f" Powiązane pliki ({nf}) zostaną trwale usunięte z biblioteki i indeksu."
        if nf
        else " W projekcie nie ma plików — usunięty zostanie tylko folder."
    )
    return {
        "confirmation_token": token,
        "expires_in_seconds": s.confirmation_token_expire_minutes * 60,
        "header_name": "X-Resource-Confirmation",
        "summary": f"Czy na pewno usunąć projekt „{p.name}”?{files_note}",
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
            "files_will_be_deleted": int(n_files or 0),
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
    stmt = select(FileAssetORM).where(
        FileAssetORM.project_id == project_id,
        FileAssetORM.user_id == user.id,
    )
    file_rows = list((await session.scalars(stmt)).all())
    storage = LocalStorage()
    for frow in file_rows:
        await purge_file_asset(session, storage, frow)
    await session.delete(p)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
