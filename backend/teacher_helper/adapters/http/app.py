from __future__ import annotations

import asyncio
import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from teacher_helper.adapters.http.routes_admin import router as admin_router
from teacher_helper.adapters.http.routes_auth import router as auth_router
from teacher_helper.adapters.http.routes_chat import router as chat_router
from teacher_helper.adapters.http.routes_conversations import router as conversations_router
from teacher_helper.adapters.http.routes_files import router as files_router
from teacher_helper.adapters.http.routes_intent import router as intent_router
from teacher_helper.adapters.http.routes_jobs import router as jobs_router
from teacher_helper.adapters.http.routes_kie import router as kie_webhook_router
from teacher_helper.adapters.http.routes_music_kie import router as music_kie_router
from teacher_helper.adapters.http.routes_privacy import router as privacy_router
from teacher_helper.adapters.http.routes_projects import router as projects_router
from teacher_helper.adapters.http.routes_sound import router as sound_router
from teacher_helper.adapters.http.routes_topics import router as topics_router
from teacher_helper.adapters.http.routes_voice import router as voice_router
from teacher_helper.config import get_settings
from teacher_helper.infrastructure.db.session import async_session_factory
from teacher_helper.infrastructure.jobs import reap_stale_running_jobs
from teacher_helper.infrastructure.retention import enforce_operational_retention

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=()"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # HSTS tylko przy HTTPS — na http://127.0.0.1 nie wysyłaj (unikniesz dziwnych zachowań w dev)
        if request.url.scheme == "https" and not get_settings().debug:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    stop_retention = asyncio.Event()

    async def retention_loop() -> None:
        interval = get_settings().retention_cleanup_interval_hours * 3600
        while not stop_retention.is_set():
            try:
                async with async_session_factory() as session:
                    removed = await enforce_operational_retention(session)
                    await session.commit()
                    if any(removed.values()):
                        logger.info("Retention cleanup removed %s", removed)
            except Exception:
                logger.exception("Retention cleanup failed")
            try:
                await asyncio.wait_for(stop_retention.wait(), timeout=interval)
            except TimeoutError:
                pass

    try:
        async with async_session_factory() as session:
            n = await reap_stale_running_jobs(session)
            if n:
                await session.commit()
                logger.info("Startup reaper marked %s stale running job(s) as error", n)
    except Exception:
        logger.exception("Startup job reaper failed")
    retention_task = asyncio.create_task(retention_loop())
    try:
        yield
    finally:
        stop_retention.set()
        await retention_task


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=s.app_name,
        version="0.3.0",
        description="TeacherHelper — modularny monolit: auth, projekty, pliki, kontekst, czat z orchestracją modułów (tool calling).",
        docs_url="/docs" if s.openapi_docs else None,
        redoc_url="/redoc" if s.openapi_docs else None,
        lifespan=_lifespan,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    raw_origins = s.cors_origins.strip()
    origins = ["*"] if raw_origins == "*" else [o.strip() for o in raw_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )
    @app.exception_handler(Exception)
    async def _unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled %s on %s %s:\n%s",
            type(exc).__name__, request.method, request.url.path,
            traceback.format_exc(),
        )
        return JSONResponse(
            status_code=500,
            content={"detail": f"Internal server error: {exc!s:.300}"},
        )

    app.include_router(kie_webhook_router)
    app.include_router(music_kie_router)
    app.include_router(sound_router)
    app.include_router(auth_router)
    app.include_router(conversations_router)
    app.include_router(projects_router)
    app.include_router(privacy_router)
    app.include_router(topics_router)
    app.include_router(files_router)
    app.include_router(chat_router)
    app.include_router(voice_router)
    app.include_router(admin_router)
    app.include_router(intent_router)
    app.include_router(jobs_router)

    @app.get("/")
    async def root() -> dict[str, str | bool]:
        return {
            "service": s.app_name,
            "health": "/api/health",
            "openapi_docs": s.openapi_docs,
            "docs": "/docs" if s.openapi_docs else "wyłączone — ustaw OPENAPI_DOCS=true w .env",
        }

    @app.get("/api/health")
    async def api_health() -> dict[str, str]:
        return {"status": "ok", "service": "teacher-helper"}

    @app.get("/api/health/ready")
    async def api_health_ready() -> JSONResponse:
        try:
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
            return JSONResponse({"status": "ok", "database": "up"})
        except Exception:
            return JSONResponse({"status": "degraded", "database": "down"}, status_code=503)

    @app.get("/health")
    async def health_legacy() -> dict[str, str]:
        return {"status": "ok"}

    return app
