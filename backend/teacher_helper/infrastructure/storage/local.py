from __future__ import annotations

import uuid
from pathlib import Path

import aiofiles

from teacher_helper.config import get_settings


class LocalStorage:
    """Adapter zapisu plików na dysk (port storage — zamiast S3 w dev)."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or get_settings().storage_root
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = self._root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    async def put(self, data: bytes, prefix: str = "") -> str:
        suffix = uuid.uuid4().hex
        key = f"{prefix.rstrip('/')}/{suffix}" if prefix else suffix
        path = self._path(key)
        async with aiofiles.open(path, "wb") as f:
            await f.write(data)
        return key

    async def get(self, key: str) -> bytes:
        path = self._root / key
        async with aiofiles.open(path, "rb") as f:
            return await f.read()

    async def delete(self, key: str) -> None:
        path = self._root / key
        if path.is_file():
            path.unlink()
