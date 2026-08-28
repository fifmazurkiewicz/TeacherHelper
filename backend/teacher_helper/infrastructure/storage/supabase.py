from __future__ import annotations

import uuid
from urllib.parse import quote

import httpx

from teacher_helper.config import get_settings


class SupabaseStorage:
    """Adapter Supabase Storage (REST API + signed URL)."""

    def __init__(self) -> None:
        s = get_settings()
        if not s.supabase_url or not s.supabase_service_role_key:
            raise RuntimeError("SUPABASE_URL i SUPABASE_SERVICE_ROLE_KEY są wymagane dla STORAGE_BACKEND=supabase")
        self._base = s.supabase_url.rstrip("/")
        self._bucket = s.supabase_storage_bucket
        self._key = s.supabase_service_role_key
        self._headers = {
            "Authorization": f"Bearer {self._key}",
            "apikey": self._key,
        }

    def _object_url(self, key: str) -> str:
        return f"{self._base}/storage/v1/object/{self._bucket}/{quote(key, safe='/')}"

    async def put(self, data: bytes, prefix: str = "", *, content_type: str = "application/octet-stream") -> str:
        suffix = uuid.uuid4().hex
        key = f"{prefix.rstrip('/')}/{suffix}" if prefix else suffix
        url = self._object_url(key)
        headers = {**self._headers, "Content-Type": content_type, "x-upsert": "true"}
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, content=data, headers=headers)
            resp.raise_for_status()
        return key

    async def get(self, key: str) -> bytes:
        url = self._object_url(key)
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(url, headers=self._headers)
            resp.raise_for_status()
            return resp.content

    async def delete(self, key: str) -> None:
        url = self._object_url(key)
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.delete(url, headers=self._headers)
            if resp.status_code not in (200, 204, 404):
                resp.raise_for_status()

    async def signed_url(self, key: str, *, expires_in: int = 3600) -> str:
        url = f"{self._base}/storage/v1/object/sign/{self._bucket}/{quote(key, safe='/')}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                headers={**self._headers, "Content-Type": "application/json"},
                json={"expiresIn": expires_in},
            )
            resp.raise_for_status()
            data = resp.json()
            signed = data.get("signedURL") or data.get("signedUrl")
            if not signed:
                raise RuntimeError("Brak signedURL w odpowiedzi Supabase Storage")
            if signed.startswith("http"):
                return signed
            return f"{self._base}/storage/v1{signed}"
