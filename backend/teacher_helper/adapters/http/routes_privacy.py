from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import PurePosixPath
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select

from teacher_helper.adapters.http.deps import ApprovedUser, DbSession
from teacher_helper.adapters.http.schemas import AccountDeleteRequest, AiDisclosureResponse
from teacher_helper.config import get_settings
from teacher_helper.infrastructure.db.models import (
    AiReadAuditORM,
    ConversationORM,
    FileAssetORM,
    LlmUsageLogORM,
    MessageORM,
    ProjectORM,
    TopicORM,
    UserORM,
)
from teacher_helper.infrastructure.jobs import GenerationJobORM, JobStatus
from teacher_helper.infrastructure.storage.factory import get_storage

router = APIRouter(prefix="/v1/privacy", tags=["privacy"])
AI_DISCLOSURE_VERSION = "2026-09-13"
DELETE_CONFIRMATION = "USUŃ MOJE KONTO"
DELETE_CONVERSATIONS_CONFIRMATION = "USUŃ ROZMOWY"
DELETE_MATERIALS_CONFIRMATION = "USUŃ MATERIAŁY"


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _rows(items: list[object], *fields: str) -> list[dict[str, object]]:
    return [{field: getattr(item, field) for field in fields} for item in items]


async def _ensure_no_active_generation(session: DbSession, user_id: UUID) -> None:
    active = await session.scalar(
        select(GenerationJobORM.id).where(
            GenerationJobORM.user_id == user_id,
            GenerationJobORM.status.in_((JobStatus.pending.value, JobStatus.running.value)),
        ).limit(1)
    )
    if active is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Poczekaj na zakończenie aktywnego generowania przed usunięciem danych.",
        )


@router.get("/ai-disclosure", response_model=AiDisclosureResponse)
async def ai_disclosure(user: ApprovedUser) -> AiDisclosureResponse:
    return AiDisclosureResponse(
        current_version=AI_DISCLOSURE_VERSION,
        acknowledged=user.ai_disclosure_version == AI_DISCLOSURE_VERSION,
        acknowledged_at=user.ai_disclosure_acknowledged_at,
    )


@router.post("/ai-disclosure", response_model=AiDisclosureResponse)
async def acknowledge_ai_disclosure(session: DbSession, user: ApprovedUser) -> AiDisclosureResponse:
    user.ai_disclosure_version = AI_DISCLOSURE_VERSION
    user.ai_disclosure_acknowledged_at = datetime.now(timezone.utc)
    await session.commit()
    return AiDisclosureResponse(
        current_version=AI_DISCLOSURE_VERSION,
        acknowledged=True,
        acknowledged_at=user.ai_disclosure_acknowledged_at,
    )


@router.get("/export")
async def export_my_data(session: DbSession, user: ApprovedUser) -> StreamingResponse:
    projects = list((await session.scalars(select(ProjectORM).where(ProjectORM.user_id == user.id))).all())
    topics = list((await session.scalars(select(TopicORM).where(TopicORM.user_id == user.id))).all())
    conversations = list(
        (await session.scalars(select(ConversationORM).where(ConversationORM.user_id == user.id))).all()
    )
    conversation_ids = [row.id for row in conversations]
    messages = (
        list((await session.scalars(select(MessageORM).where(MessageORM.conversation_id.in_(conversation_ids)))).all())
        if conversation_ids
        else []
    )
    files = list((await session.scalars(select(FileAssetORM).where(FileAssetORM.user_id == user.id))).all())
    audits = list((await session.scalars(select(AiReadAuditORM).where(AiReadAuditORM.user_id == user.id))).all())
    usage = list((await session.scalars(select(LlmUsageLogORM).where(LlmUsageLogORM.user_id == user.id))).all())

    manifest = {
        "exported_at": datetime.now(timezone.utc),
        "account": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "created_at": user.created_at,
            "ai_disclosure_version": user.ai_disclosure_version,
            "ai_disclosure_acknowledged_at": user.ai_disclosure_acknowledged_at,
        },
        "projects": _rows(projects, "id", "name", "description", "created_at"),
        "topics": _rows(topics, "id", "name", "description", "created_at"),
        "conversations": _rows(conversations, "id", "project_id", "title", "created_at", "updated_at"),
        "messages": _rows(messages, "id", "conversation_id", "role", "content", "extra", "created_at"),
        "files": _rows(
            files, "id", "project_id", "topic_id", "name", "category", "mime_type", "version", "size_bytes", "created_at"
        ),
        "ai_read_audit": _rows(audits, "id", "file_asset_id", "purpose", "created_at"),
        "llm_usage": _rows(
            usage, "id", "provider", "model", "call_kind", "module_name", "prompt_tokens", "completion_tokens", "total_tokens", "cost_usd", "created_at"
        ),
    }

    output = BytesIO()
    storage = get_storage()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("teacher-helper-data.json", json.dumps(manifest, ensure_ascii=False, indent=2, default=_json_default))
        for file_row in files:
            try:
                content = await storage.get(file_row.storage_key)
            except Exception:
                continue
            safe_name = PurePosixPath(file_row.name).name or str(file_row.id)
            archive.writestr(f"files/{file_row.id}-{safe_name}", content)
    output.seek(0)
    headers = {"Content-Disposition": 'attachment; filename="teacher-helper-data.zip"'}
    return StreamingResponse(output, media_type="application/zip", headers=headers)


async def _delete_supabase_identity(user_id: UUID) -> None:
    settings = get_settings()
    if not settings.supabase_url:
        return
    if not settings.supabase_service_role_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Usuwanie konta jest chwilowo niedostępne")
    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.delete(url, headers=headers)
    if response.status_code not in (200, 204, 404):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="Nie udało się usunąć konta uwierzytelniania")


@router.delete("/account", response_model=None)
async def delete_my_account(session: DbSession, user: ApprovedUser, body: AccountDeleteRequest) -> Response:
    if body.confirmation != DELETE_CONFIRMATION:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f'Wpisz dokładnie: {DELETE_CONFIRMATION}')

    await _ensure_no_active_generation(session, user.id)
    files = list((await session.scalars(select(FileAssetORM).where(FileAssetORM.user_id == user.id))).all())
    storage = get_storage()
    for file_row in files:
        try:
            await storage.delete(file_row.storage_key)
        except Exception as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Nie udało się usunąć pliku {file_row.name}") from exc

    await _delete_supabase_identity(user.id)
    await session.execute(delete(UserORM).where(UserORM.id == user.id))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/conversations", response_model=None)
async def delete_all_conversations(
    session: DbSession, user: ApprovedUser, body: AccountDeleteRequest
) -> Response:
    if body.confirmation != DELETE_CONVERSATIONS_CONFIRMATION:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Wymagane potwierdzenie: {DELETE_CONVERSATIONS_CONFIRMATION}",
        )
    await _ensure_no_active_generation(session, user.id)
    await session.execute(delete(ConversationORM).where(ConversationORM.user_id == user.id))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/materials", response_model=None)
async def delete_all_materials(session: DbSession, user: ApprovedUser, body: AccountDeleteRequest) -> Response:
    if body.confirmation != DELETE_MATERIALS_CONFIRMATION:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Wymagane potwierdzenie: {DELETE_MATERIALS_CONFIRMATION}",
        )
    await _ensure_no_active_generation(session, user.id)
    files = list((await session.scalars(select(FileAssetORM).where(FileAssetORM.user_id == user.id))).all())
    storage = get_storage()
    for file_row in files:
        try:
            await storage.delete(file_row.storage_key)
        except Exception as exc:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                detail=f"Nie udało się usunąć pliku {file_row.name}",
            ) from exc
    await session.execute(delete(FileAssetORM).where(FileAssetORM.user_id == user.id))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
