from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class FileCategory(str, Enum):
    SCENARIO = "scenario"
    GRAPHIC = "graphic"
    VIDEO = "video"
    MUSIC = "music"
    POETRY = "poetry"
    PRESENTATION = "presentation"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class UserId:
    value: UUID


@dataclass(frozen=True, slots=True)
class ProjectId:
    value: UUID


@dataclass(slots=True)
class FileAsset:
    """Metadane pliku w bazie użytkownika (blob w storage — osobno)."""

    id: UUID = field(default_factory=uuid4)
    owner_id: UUID | None = None
    project_id: UUID | None = None
    name: str = ""
    category: FileCategory = FileCategory.OTHER
    mime_type: str = ""
    version: int = 1
    extra: dict[str, Any] = field(default_factory=dict)
