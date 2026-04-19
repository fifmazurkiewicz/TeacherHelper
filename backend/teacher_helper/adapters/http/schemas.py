from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None
    role: str

    model_config = {"from_attributes": True}


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    description: str | None = None


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FileResponse(BaseModel):
    id: UUID
    name: str
    category: str
    mime_type: str
    version: int
    size_bytes: int
    project_id: UUID | None
    topic_id: UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MoveFilesRequest(BaseModel):
    """Przeniesienie plików do innego katalogu (``project_id`` null = „Inne pliki”)."""

    file_ids: list[UUID] = Field(min_length=1, max_length=500)
    project_id: UUID | None = None


class KieMusicImportByTaskRequest(BaseModel):
    """Pobranie MP3 z KIE po ``taskId`` (record-info + download) — z UI „Moje materiały”."""

    task_id: str = Field(min_length=4, max_length=200, description="Identyfikator zadania z odpowiedzi generate / pliku .txt")
    project_id: UUID | None = Field(default=None, description="Opcjonalny projekt docelowy")


class TopicCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    description: str | None = Field(None, max_length=8000)


class TopicResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TopicSearchHit(BaseModel):
    text: str
    score: float
    file_id: UUID
    chunk_index: int
    file_name: str


class FileReindexDryRunResponse(BaseModel):
    dry_run: Literal[True] = True
    would_reindex: Literal[True] = True
    file_id: str
    current_chunks: int


class ChatHistoryEntry(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=32000)
    conversation_id: UUID | None = None
    project_id: UUID | None = None
    attached_file_ids: list[UUID] | None = None
    history: list[ChatHistoryEntry] | None = None
    dry_run: bool = False


class PendingProjectAction(BaseModel):
    """Propozycja utworzenia / usunięcia projektu — wymaga potwierdzenia w UI (token jak przy prepare-delete)."""

    confirmation_token: str
    expires_in_seconds: int
    summary: str
    name: str | None = None
    description: str | None = None
    project_id: str | None = None
    project_name: str | None = None


class CreatedFileBrief(BaseModel):
    """Skrót pliku zapisanego w tej turze czatu — do przycisków „Pobierz” w UI."""

    id: UUID
    name: str
    mime_type: str


class ChatResponse(BaseModel):
    reply: str
    conversation_id: UUID
    created_file_ids: list[UUID]
    run_modules: list[str]
    created_files: list[CreatedFileBrief] = Field(default_factory=list)
    needs_clarification: bool
    clarification_question: str | None = None
    dry_run: bool = False
    side_effects_skipped: bool = False
    linked_project_id: UUID | None = None
    pending_project_creation: PendingProjectAction | None = None
    pending_project_deletion: PendingProjectAction | None = None


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=500)


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    project_id: UUID | None = Field(default=None, description="Przypisanie rozmowy do katalogu (projektu); null = odłącz")


class ConversationResponse(BaseModel):
    id: UUID
    title: str
    project_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime
    extra: dict | None = None

    model_config = {"from_attributes": True}


class AnalyzeIntentRequest(BaseModel):
    message: str = Field(min_length=1)
