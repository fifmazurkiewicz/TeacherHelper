from __future__ import annotations

from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select

from teacher_helper.adapters.http.deps import CurrentUser, DbSession
from teacher_helper.adapters.http.rate_limit import check_rate_limit
from teacher_helper.adapters.http.schemas import FileReindexDryRunResponse, FileResponse, MoveFilesRequest
from teacher_helper.config import get_settings
from teacher_helper.infrastructure.db.file_ops import index_file_content, purge_file_asset
from teacher_helper.infrastructure.db.models import (
    FileAssetORM,
    FileCategory,
    FileChunkORM,
    FileStatus,
    ProjectORM,
    TopicORM,
)
from teacher_helper.infrastructure.storage.local import LocalStorage
from teacher_helper.security.resource_confirmation import (
    ACTION_DELETE_FILE,
    ACTION_REINDEX_FILE,
    RESOURCE_FILE,
    create_resource_confirmation_token,
    verify_resource_confirmation_token,
)

router = APIRouter(prefix="/v1/files", tags=["files"])
_storage = LocalStorage()


def _content_disposition_attachment(filename: str) -> str:
    """RFC 5987 ``filename*`` (UTF-8) + prosty ``filename`` ASCII — Starlette wymaga latin-1 w nagłówkach."""
    enc = quote(filename, safe="")
    fallback = filename.encode("ascii", "replace").decode("ascii").replace("?", "_")
    fallback = "".join(c for c in fallback if c not in '"\\')[:200]
    if not fallback.strip(" ."):
        fallback = "download"
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{enc}"


def _parse_category(raw: str | None) -> FileCategory:
    if not raw:
        return FileCategory.other
    try:
        return FileCategory(raw)
    except ValueError:
        return FileCategory.other


@router.post("", response_model=FileResponse)
async def upload_file(
    session: DbSession,
    user: CurrentUser,
    file: UploadFile = File(...),
    project_id: str | None = Form(None),
    topic_id: str | None = Form(None),
    category: str | None = Form(None),
) -> FileAssetORM:
    check_rate_limit(user)
    pid: UUID | None = None
    tid: UUID | None = None
    if project_id:
        try:
            pid = UUID(project_id)
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Nieprawidłowy project_id")
        proj = await session.get(ProjectORM, pid)
        if not proj or proj.user_id != user.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Projekt nie należy do użytkownika")
    if topic_id:
        try:
            tid = UUID(topic_id)
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Nieprawidłowy topic_id")
        top = await session.get(TopicORM, tid)
        if not top or top.user_id != user.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Temat nie należy do użytkownika")
    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Maks. 50 MB")
    key = await _storage.put(raw, prefix=f"u/{user.id}")
    name = file.filename or "upload.bin"
    mime = file.content_type or "application/octet-stream"
    row = FileAssetORM(
        id=uuid4(),
        user_id=user.id,
        project_id=pid,
        topic_id=tid,
        name=name,
        category=_parse_category(category),
        mime_type=mime,
        storage_key=key,
        version=1,
        size_bytes=len(raw),
        status=FileStatus.draft,
    )
    session.add(row)
    await session.flush()
    await index_file_content(session, row, raw, name)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("", response_model=list[FileResponse])
async def list_files(
    session: DbSession,
    user: CurrentUser,
    project_id: UUID | None = None,
    topic_id: UUID | None = None,
) -> list[FileAssetORM]:
    stmt = select(FileAssetORM).where(FileAssetORM.user_id == user.id)
    if project_id is not None:
        stmt = stmt.where(FileAssetORM.project_id == project_id)
    if topic_id is not None:
        stmt = stmt.where(FileAssetORM.topic_id == topic_id)
    stmt = stmt.order_by(FileAssetORM.created_at.desc())
    return list((await session.scalars(stmt)).all())


@router.post("/move", response_model=list[FileResponse])
async def move_files(session: DbSession, user: CurrentUser, body: MoveFilesRequest) -> list[FileAssetORM]:
    check_rate_limit(user)
    target_pid = body.project_id
    if target_pid is not None:
        proj = await session.get(ProjectORM, target_pid)
        if not proj or proj.user_id != user.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Projekt nie znaleziony")

    ids_ordered = list(dict.fromkeys(body.file_ids))
    stmt = select(FileAssetORM).where(FileAssetORM.user_id == user.id, FileAssetORM.id.in_(ids_ordered))
    found = list((await session.scalars(stmt)).all())
    if len(found) != len(ids_ordered):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Niektóre pliki nie istnieją lub nie należą do Ciebie.",
        )
    by_id = {r.id: r for r in found}
    ordered = [by_id[fid] for fid in ids_ordered]
    for row in ordered:
        if row.project_id != target_pid:
            row.project_id = target_pid
            row.topic_id = None
    await session.commit()
    for row in ordered:
        await session.refresh(row)
    return ordered


@router.get("/{file_id}/delete-impact")
async def file_delete_impact(session: DbSession, user: CurrentUser, file_id: UUID) -> dict:
    row = await session.get(FileAssetORM, file_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Plik nie znaleziony")
    chunks = await session.scalar(
        select(func.count()).select_from(FileChunkORM).where(FileChunkORM.file_asset_id == file_id)
    )
    return {
        "resource": "file",
        "file_id": str(file_id),
        "name": row.name,
        "size_bytes": row.size_bytes,
        "indexed_chunks": int(chunks or 0),
        "message": "Usunięcie jest nieodwracalne (plik w storage i indeks fragmentów). Użyj prepare-delete, potem DELETE z nagłówkiem X-Resource-Confirmation.",
    }


@router.post("/{file_id}/prepare-delete")
async def file_prepare_delete(session: DbSession, user: CurrentUser, file_id: UUID) -> dict:
    row = await session.get(FileAssetORM, file_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Plik nie znaleziony")
    s = get_settings()
    token = create_resource_confirmation_token(
        user_id=user.id,
        action=ACTION_DELETE_FILE,
        resource_type=RESOURCE_FILE,
        resource_id=file_id,
    )
    return {
        "confirmation_token": token,
        "expires_in_seconds": s.confirmation_token_expire_minutes * 60,
        "header_name": "X-Resource-Confirmation",
        "summary": f"Czy na pewno usunąć plik „{row.name}”? Tej operacji nie można cofnąć.",
    }


@router.post("/{file_id}/prepare-reindex")
async def file_prepare_reindex(session: DbSession, user: CurrentUser, file_id: UUID) -> dict:
    row = await session.get(FileAssetORM, file_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Plik nie znaleziony")
    s = get_settings()
    token = create_resource_confirmation_token(
        user_id=user.id,
        action=ACTION_REINDEX_FILE,
        resource_type=RESOURCE_FILE,
        resource_id=file_id,
    )
    return {
        "confirmation_token": token,
        "expires_in_seconds": s.confirmation_token_expire_minutes * 60,
        "header_name": "X-Resource-Confirmation",
        "summary": f"Ponownie zbudować indeks tekstowy (fragmenty) dla „{row.name}”? Istniejące chunki zostaną zastąpione.",
    }


@router.get("/{file_id}/download")
async def download_file(session: DbSession, user: CurrentUser, file_id: UUID) -> Response:
    row = await session.get(FileAssetORM, file_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Plik nie znaleziony")
    data = await _storage.get(row.storage_key)
    return Response(
        content=data,
        media_type=row.mime_type,
        headers={"Content-Disposition": _content_disposition_attachment(row.name)},
    )


@router.post("/{file_id}/reindex", response_model=FileResponse | FileReindexDryRunResponse)
async def reindex_file(
    session: DbSession,
    user: CurrentUser,
    file_id: UUID,
    dry_run: bool = False,
    x_resource_confirmation: str | None = Header(None, alias="X-Resource-Confirmation"),
) -> FileAssetORM | FileReindexDryRunResponse:
    row = await session.get(FileAssetORM, file_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Plik nie znaleziony")
    s = get_settings()
    if dry_run:
        n = await session.scalar(
            select(func.count()).select_from(FileChunkORM).where(FileChunkORM.file_asset_id == file_id)
        )
        return FileReindexDryRunResponse(
            file_id=str(file_id),
            current_chunks=int(n or 0),
        )
    if s.require_resource_confirmation:
        tok = x_resource_confirmation or ""
        if not verify_resource_confirmation_token(
            tok,
            user_id=user.id,
            action=ACTION_REINDEX_FILE,
            resource_type=RESOURCE_FILE,
            resource_id=file_id,
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "code": "CONFIRMATION_REQUIRED",
                    "message": "Potwierdź modyfikację indeksu — wywołaj POST /v1/files/{id}/prepare-reindex i powtórz z nagłówkiem X-Resource-Confirmation.",
                },
            )
    raw = await _storage.get(row.storage_key)
    await index_file_content(session, row, raw, row.name)
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/{file_id}", response_model=None)
async def delete_file(
    session: DbSession,
    user: CurrentUser,
    file_id: UUID,
    dry_run: bool = False,
    x_resource_confirmation: str | None = Header(None, alias="X-Resource-Confirmation"),
) -> Response | dict:
    row = await session.get(FileAssetORM, file_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Plik nie znaleziony")
    s = get_settings()
    if dry_run:
        chunks = await session.scalar(
            select(func.count()).select_from(FileChunkORM).where(FileChunkORM.file_asset_id == file_id)
        )
        return {
            "dry_run": True,
            "would_delete": True,
            "file_id": str(file_id),
            "name": row.name,
            "indexed_chunks": int(chunks or 0),
        }
    if s.require_resource_confirmation:
        tok = x_resource_confirmation or ""
        if not verify_resource_confirmation_token(
            tok,
            user_id=user.id,
            action=ACTION_DELETE_FILE,
            resource_type=RESOURCE_FILE,
            resource_id=file_id,
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "code": "CONFIRMATION_REQUIRED",
                    "message": "Potwierdź usunięcie — POST /v1/files/{id}/prepare-delete, potem DELETE z nagłówkiem X-Resource-Confirmation.",
                },
            )
    await purge_file_asset(session, _storage, row)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{file_id}/export")
async def export_file(
    session: DbSession,
    user: CurrentUser,
    file_id: UUID,
    target_format: str = "pdf",
) -> Response:
    """Eksport pliku do formatu txt/pdf/docx — konwersja z wyodrębnionego tekstu."""
    from teacher_helper.infrastructure.export import SUPPORTED_FORMATS, convert_text
    from teacher_helper.infrastructure.text_extract import extract_plain_text

    row = await session.get(FileAssetORM, file_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Plik nie znaleziony")

    fmt = target_format.lower().strip().lstrip(".")
    if fmt not in SUPPORTED_FORMATS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Nieobsługiwany format: {fmt}. Dostępne: {', '.join(SUPPORTED_FORMATS)}",
        )

    raw = await _storage.get(row.storage_key)
    text = extract_plain_text(raw, row.mime_type, row.name)
    if not text.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nie udało się wyodrębnić tekstu z pliku — eksport niemożliwy.",
        )

    title = row.name.rsplit(".", 1)[0] if "." in row.name else row.name
    out_bytes, mime = convert_text(text, fmt, title=title)
    out_name = f"{title}.{fmt}"

    return Response(
        content=out_bytes,
        media_type=mime,
        headers={"Content-Disposition": _content_disposition_attachment(out_name)},
    )
