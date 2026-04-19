from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, BigInteger, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from teacher_helper.infrastructure.db.base import Base


class UserRole(str, enum.Enum):
    teacher = "teacher"
    admin = "admin"


class FileCategory(str, enum.Enum):
    scenario = "scenario"
    graphic = "graphic"
    video = "video"
    music = "music"
    poetry = "poetry"
    presentation = "presentation"
    other = "other"


class FileStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"


class UserORM(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="userrole", create_type=False), default=UserRole.teacher, nullable=False
    )
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    rate_limit_rpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # NULL = domyślny limit z konfiguracji; 0 = brak limitu per konto (tylko limity globalne); >0 = własny sufit.
    llm_daily_token_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    projects: Mapped[list[ProjectORM]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    topics: Mapped[list["TopicORM"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    files: Mapped[list[FileAssetORM]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    conversations: Mapped[list["ConversationORM"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class ProjectORM(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped[UserORM] = relationship(back_populates="projects")
    files: Mapped[list[FileAssetORM]] = relationship(back_populates="project")
    conversations: Mapped[list["ConversationORM"]] = relationship(back_populates="project")


class ConversationORM(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    owner: Mapped[UserORM] = relationship(back_populates="conversations")
    project: Mapped[ProjectORM | None] = relationship(back_populates="conversations")
    messages: Mapped[list["MessageORM"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class TopicORM(Base):
    """Temat Omówienie tematu — izolacja plików i wektorów po topic_id."""

    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped[UserORM] = relationship(back_populates="topics")
    files: Mapped[list["FileAssetORM"]] = relationship(back_populates="topic")


class MessageORM(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[ConversationORM] = relationship(back_populates="messages")


class FileAssetORM(Base):
    __tablename__ = "file_assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[FileCategory] = mapped_column(
        Enum(FileCategory, name="filecategory", create_type=False), default=FileCategory.other
    )
    mime_type: Mapped[str] = mapped_column(String(200), default="text/plain")
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("file_assets.id", ondelete="SET NULL"), nullable=True
    )
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[FileStatus] = mapped_column(
        Enum(FileStatus, name="filestatus", create_type=False), default=FileStatus.draft
    )
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped[UserORM] = relationship(back_populates="files")
    project: Mapped[ProjectORM | None] = relationship(back_populates="files")
    topic: Mapped["TopicORM | None"] = relationship(back_populates="files")
    chunks: Mapped[list[FileChunkORM]] = relationship(back_populates="file_asset", cascade="all, delete-orphan")


class FileChunkORM(Base):
    __tablename__ = "file_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("file_assets.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(JSONB, nullable=False)

    file_asset: Mapped[FileAssetORM] = relationship(back_populates="chunks")


class AiReadAuditORM(Base):
    __tablename__ = "ai_read_audit"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    file_asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("file_assets.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(200), default="context")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LlmUsageLogORM(Base):
    """Jedna linia na każde wywołanie LLM (tokeny + model dla panelu admina)."""

    __tablename__ = "llm_usage_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    call_kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    module_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SystemIncidentORM(Base):
    """Zdarzenia awarii / przekroczeń — podgląd w panelu admina i podstawa pod alerty."""

    __tablename__ = "system_incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
