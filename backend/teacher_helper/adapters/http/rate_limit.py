from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, status

from teacher_helper.config import get_settings
from teacher_helper.infrastructure.db.models import UserORM

_window_sec = 60
_fallback_buckets: dict[str, deque[float]] = defaultdict(deque)


def _get_redis():
    """Leniwa inicjalizacja klienta Redis (None jeśli niedostępny)."""
    try:
        import redis
        s = get_settings()
        client = redis.from_url(s.redis_url, decode_responses=True, socket_connect_timeout=2)
        client.ping()
        return client
    except Exception:
        return None


_redis_client: object | None = ...


def _redis():
    global _redis_client
    if _redis_client is ...:
        _redis_client = _get_redis()
    return _redis_client


def check_rate_limit(user: UserORM) -> None:
    limit = user.rate_limit_rpm if user.rate_limit_rpm is not None else get_settings().default_rate_limit_rpm
    key = f"rate_limit:{user.id}"

    r = _redis()
    if r is not None:
        _check_redis(r, key, limit)
    else:
        _check_in_memory(str(user.id), limit)


def _check_redis(r, key: str, limit: int) -> None:  # type: ignore[type-arg]
    import redis as redis_lib

    pipe = r.pipeline()
    now_ms = int(time.time() * 1000)
    window_ms = _window_sec * 1000

    pipe.zremrangebyscore(key, 0, now_ms - window_ms)
    pipe.zcard(key)
    pipe.zadd(key, {str(now_ms): now_ms})
    pipe.expire(key, _window_sec + 5)
    results = pipe.execute()

    current_count = results[1]
    if current_count >= limit:
        r.zrem(key, str(now_ms))
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Zbyt wiele żądań (limit: {limit}/min) — spróbuj za chwilę.",
        )


def _check_in_memory(user_key: str, limit: int) -> None:
    now = time.time()
    dq = _fallback_buckets[user_key]
    while dq and now - dq[0] > _window_sec:
        dq.popleft()
    if len(dq) >= limit:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Zbyt wiele żądań (limit: {limit}/min) — spróbuj za chwilę.",
        )
    dq.append(now)
