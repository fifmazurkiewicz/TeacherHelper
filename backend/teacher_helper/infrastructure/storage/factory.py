from __future__ import annotations

from teacher_helper.config import get_settings
from teacher_helper.infrastructure.storage.local import LocalStorage
from teacher_helper.infrastructure.storage.supabase import SupabaseStorage

_storage_instance: LocalStorage | SupabaseStorage | None = None


def get_storage() -> LocalStorage | SupabaseStorage:
    global _storage_instance
    if _storage_instance is None:
        backend = get_settings().storage_backend.lower().strip()
        if backend == "supabase":
            _storage_instance = SupabaseStorage()
        else:
            _storage_instance = LocalStorage()
    return _storage_instance


def reset_storage_for_tests() -> None:
    global _storage_instance
    _storage_instance = None
