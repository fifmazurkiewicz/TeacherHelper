from __future__ import annotations

import logging
import traceback

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from teacher_helper.adapters.http.routes_admin import router as admin_router
from teacher_helper.adapters.http.routes_auth import router as auth_router
from teacher_helper.adapters.http.routes_chat import router as chat_router
from teacher_helper.adapters.http.routes_conversations import router as conversations_router
from teacher_helper.adapters.http.routes_files import router as files_router
from teacher_helper.adapters.http.routes_intent import router as intent_router
from teacher_helper.adapters.http.routes_kie import router as kie_webhook_router
from teacher_helper.adapters.http.routes_music_kie import router as music_kie_router
from teacher_helper.adapters.http.routes_projects import router as projects_router
from teacher_helper.adapters.http.routes_topics import router as topics_router
from teacher_helper.config import get_settings

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # HSTS tylko przy HTTPS — na http://127.0.0.1 nie wysyłaj (unikniesz dziwnych zachowań w dev)
        if request.url.scheme == "https" and not get_settings().debug:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=s.app_name,
        version="0.3.0",
        description="TeacherHelper — modularny monolit: auth, projekty, pliki, kontekst, czat z orchestracją modułów (tool calling).",
        docs_url="/docs" if s.openapi_docs else None,
        redoc_url="/redoc" if s.openapi_docs else None,
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
    app.include_router(auth_router)
    app.include_router(conversations_router)
    app.include_router(projects_router)
    app.include_router(topics_router)
    app.include_router(files_router)
    app.include_router(chat_router)
    app.include_router(admin_router)
    app.include_router(intent_router)

    @app.on_event("startup")
    async def _startup() -> None:
        from teacher_helper.infrastructure.qdrant import ensure_collection
        try:
            ensure_collection()
        except Exception:
            import logging
            logging.getLogger(__name__).warning("Qdrant niedostępny — kolekcja nie została utworzona")

    @app.get("/")
    async def root() -> dict[str, str | bool]:
        return {
            "service": s.app_name,
            "health": "/health",
            "openapi_docs": s.openapi_docs,
            "docs": "/docs" if s.openapi_docs else "wyłączone — ustaw OPENAPI_DOCS=true w .env",
        }

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
