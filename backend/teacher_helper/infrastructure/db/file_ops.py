from __future__ import annotations

import uuid
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from teacher_helper.infrastructure.chunking import chunk_text
from teacher_helper.infrastructure.db.models import (
    AiReadAuditORM,
    FileAssetORM,
    FileChunkORM,
    FileCategory,
    FileStatus,
)
from teacher_helper.infrastructure.embeddings import embed_text, embed_texts
from teacher_helper.infrastructure.qdrant import delete_file_vectors, search_vectors, upsert_chunks
from teacher_helper.infrastructure.text_extract import extract_plain_text


async def delete_chunks_for_file(session: AsyncSession, file_id: UUID) -> None:
    await session.execute(delete(FileChunkORM).where(FileChunkORM.file_asset_id == file_id))
    delete_file_vectors(file_id)


class _StorageDeletePort(Protocol):
    async def delete(self, key: str) -> None: ...


async def purge_file_asset(session: AsyncSession, storage: _StorageDeletePort, row: FileAssetORM) -> None:
    """Usuwa chunki (Postgres + Qdrant), blob storage i wiersz pliku — jedna ścieżka z ``routes_files`` i przy usuwaniu projektu."""
    await delete_chunks_for_file(session, row.id)
    await storage.delete(row.storage_key)
    await session.delete(row)


async def index_file_content(
    session: AsyncSession,
    file_row: FileAssetORM,
    raw: bytes,
    filename: str,
) -> None:
    text = extract_plain_text(raw, file_row.mime_type, filename)
    if not text.strip():
        return
    await delete_chunks_for_file(session, file_row.id)
    chunks = chunk_text(text)
    if not chunks:
        return
    embeddings = await embed_texts(chunks)
    chunk_ids: list[UUID] = []
    for idx, (chunk, emb) in enumerate(zip(chunks, embeddings, strict=True)):
        cid = uuid.uuid4()
        chunk_ids.append(cid)
        session.add(
            FileChunkORM(
                id=cid,
                file_asset_id=file_row.id,
                chunk_index=idx,
                text=chunk,
                embedding=emb,
            )
        )

    upsert_chunks(
        file_asset_id=file_row.id,
        user_id=file_row.user_id,
        chunk_ids=chunk_ids,
        texts=chunks,
        embeddings=embeddings,
        topic_id=file_row.topic_id,
    )


async def semantic_search_chunks(
    session: AsyncSession,
    user_id: UUID,
    query: str,
    top_k: int = 8,
    project_id: UUID | None = None,
    topic_id: UUID | None = None,
) -> list[tuple[FileChunkORM, float]]:
    """Wyszukiwanie semantyczne przez Qdrant + doładowanie ORM z PostgreSQL.

    - ``topic_id`` ustawione: tylko chunki należące do tego tematu (filtr Qdrant + weryfikacja ORM).
    - ``topic_id`` None (asystent / biblioteka): tylko pliki **bez** ``file_assets.topic_id`` — szersze
      pobranie z Qdrant (tylko user_id), odfiltrowanie po DB, żeby nie mieszać z Omówieniem tematu.
    """
    q_emb = await embed_text(query)
    if topic_id is not None:
        hits = search_vectors(q_emb, user_id, top_k=top_k, topic_id=topic_id)
    else:
        hits = search_vectors(q_emb, user_id, top_k=min(top_k * 4, 48), topic_id=None)

    result: list[tuple[FileChunkORM, float]] = []
    for hit in hits:
        chunk_id = hit["id"]
        try:
            uid = UUID(chunk_id)
        except ValueError:
            continue
        chunk = await session.get(
            FileChunkORM, uid,
            options=[selectinload(FileChunkORM.file_asset)],
        )
        if chunk is None or chunk.file_asset is None:
            continue
        if chunk.file_asset.user_id != user_id:
            continue
        if topic_id is not None:
            if chunk.file_asset.topic_id != topic_id:
                continue
        else:
            if chunk.file_asset.topic_id is not None:
                continue
        if project_id is not None and chunk.file_asset.project_id != project_id:
            continue
        result.append((chunk, hit["score"]))
        if len(result) >= top_k:
            break

    return result


async def load_attached_context(
    session: AsyncSession,
    user_id: UUID,
    file_ids: list[UUID],
    query_for_audit: str,
) -> str:
    if not file_ids:
        return ""
    parts: list[str] = []
    for fid in file_ids:
        row = await session.get(FileAssetORM, fid)
        if not row or row.user_id != user_id:
            continue
        session.add(
            AiReadAuditORM(
                id=uuid.uuid4(),
                user_id=user_id,
                file_asset_id=fid,
                purpose="chat_context",
            )
        )
        stmt = (
            select(FileChunkORM)
            .where(FileChunkORM.file_asset_id == fid)
            .order_by(FileChunkORM.chunk_index)
        )
        chs = (await session.scalars(stmt)).all()
        if chs:
            text = "\n".join(c.text for c in chs)
        else:
            text = "(brak indeksu — prześlij plik ponownie lub użytek nieobsługiwany)"
        parts.append(f"--- Plik: {row.name} ---\n{text[:12000]}")
    return "\n\n".join(parts)


def category_for_module(module: str) -> FileCategory:
    m = module.lower().strip()
    mapping = {
        "scenario": FileCategory.scenario,
        "graphics": FileCategory.graphic,
        "graphic": FileCategory.graphic,
        "video": FileCategory.video,
        "music": FileCategory.music,
        "poetry": FileCategory.poetry,
        "presentation": FileCategory.presentation,
        "study": FileCategory.other,
        "export": FileCategory.other,
    }
    return mapping.get(m, FileCategory.other)


async def persist_export_as_new_file(
    session: AsyncSession,
    user_id: UUID,
    source_file_id: UUID,
    project_id: UUID | None,
    target_format: str,
    storage: Any,
) -> UUID:
    """Eksportuje treść pliku źródłowego do nowego pliku w bibliotece (PDF/DOCX/TXT/PPTX)."""
    from teacher_helper.infrastructure.export import SUPPORTED_FORMATS, convert_text
    from teacher_helper.infrastructure.text_extract import extract_plain_text

    fmt = target_format.lower().strip().lstrip(".")
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"Nieobsługiwany format: {fmt}")

    row = await session.get(FileAssetORM, source_file_id)
    if not row or row.user_id != user_id:
        raise ValueError("Plik nie znaleziony")

    raw = await storage.get(row.storage_key)
    text = extract_plain_text(raw, row.mime_type, row.name)
    if not text.strip():
        raise ValueError("Brak tekstu do eksportu")

    title = row.name.rsplit(".", 1)[0] if "." in row.name else row.name
    out_bytes, mime = convert_text(text, fmt, title=title)
    out_name = f"{title}.{fmt}"
    key = await storage.put(out_bytes, prefix=f"u/{user_id}")
    new_row = FileAssetORM(
        id=uuid.uuid4(),
        user_id=user_id,
        project_id=project_id,
        name=out_name,
        category=FileCategory.other,
        mime_type=mime,
        storage_key=key,
        version=1,
        size_bytes=len(out_bytes),
        status=FileStatus.draft,
        extra={"source_file_id": str(source_file_id), "export_format": fmt},
    )
    session.add(new_row)
    await session.flush()
    await index_file_content(session, new_row, out_bytes, out_name)
    return new_row.id
