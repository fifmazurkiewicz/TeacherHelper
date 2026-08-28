"""Weryfikacja JWT Supabase Auth (JWKS)."""
from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

import httpx
from jose import JWTError, jwt

from teacher_helper.config import get_settings

logger = logging.getLogger(__name__)

_jwks_cache: dict[str, Any] | None = None
_jwks_fetched_at: float = 0.0
_JWKS_TTL_SEC = 3600


async def _fetch_jwks() -> dict[str, Any]:
    global _jwks_cache, _jwks_fetched_at
    now = time.time()
    if _jwks_cache is not None and now - _jwks_fetched_at < _JWKS_TTL_SEC:
        return _jwks_cache

    s = get_settings()
    jwks_url = s.supabase_jwks_url
    if not jwks_url and s.supabase_url:
        jwks_url = f"{s.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    if not jwks_url:
        raise RuntimeError("Brak SUPABASE_JWKS_URL lub SUPABASE_URL — nie można zweryfikować tokenów")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(jwks_url)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_fetched_at = now
        return _jwks_cache


def _audience_ok(aud: Any, expected: str | None) -> bool:
    if not expected:
        return True
    if aud is None:
        return True
    if isinstance(aud, str):
        return aud == expected
    if isinstance(aud, list):
        return expected in aud
    return False


async def verify_supabase_access_token(token: str) -> dict[str, Any] | None:
    """Zwraca payload JWT po weryfikacji lub None."""
    s = get_settings()
    try:
        jwks = await _fetch_jwks()
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256", "ES256"],
            audience=s.supabase_jwt_audience or "authenticated",
            options={"verify_aud": bool(s.supabase_jwt_audience or True)},
        )
        if not _audience_ok(payload.get("aud"), s.supabase_jwt_audience or "authenticated"):
            return None
        sub = payload.get("sub")
        if not sub:
            return None
        UUID(str(sub))
        return payload
    except (JWTError, ValueError, httpx.HTTPError) as exc:
        logger.debug("Nieudana weryfikacja tokena Supabase: %s", exc)
        return None


def extract_user_id_from_payload(payload: dict[str, Any]) -> UUID:
    return UUID(str(payload["sub"]))
