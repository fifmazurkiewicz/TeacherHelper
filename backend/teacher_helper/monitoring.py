"""Opt-in error monitoring. Application content never leaves through Sentry."""

from __future__ import annotations

import logging
import os
import re
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlsplit

import sentry_sdk
from sentry_sdk.integrations.atexit import AtexitIntegration
from sentry_sdk.integrations.dedupe import DedupeIntegration
from sentry_sdk.integrations.excepthook import ExcepthookIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.threading import ThreadingIntegration
from sentry_sdk.transport import Transport

if TYPE_CHECKING:
    from sentry_sdk._types import Event, Hint

_CODE_ROOT = Path(__file__).resolve().parent
_ERROR_TYPES = {
    "ArithmeticError",
    "AssertionError",
    "AttributeError",
    "ConnectionError",
    "FileNotFoundError",
    "IndexError",
    "KeyError",
    "LookupError",
    "MemoryError",
    "NotImplementedError",
    "OSError",
    "OverflowError",
    "PermissionError",
    "RuntimeError",
    "TimeoutError",
    "TypeError",
    "ValueError",
    "ZeroDivisionError",
}
_ENVIRONMENTS = {"development", "test", "preview", "staging", "production"}


def _valid_dsn(value: str) -> bool:
    try:
        url = urlsplit(value)
        return bool(
            url.scheme == "https"
            and url.hostname
            and url.hostname.endswith(".ingest.de.sentry.io")
            and re.fullmatch(r"[a-f0-9]{32}", url.username or "")
            and re.fullmatch(r"/[0-9]+", url.path)
            and not url.password
            and not url.query
            and not url.fragment
            and url.port in (None, 443)
        )
    except ValueError:
        return False


def _private_event(
    event: Event,
    hint: Hint,
    *,
    component: str,
) -> Event | None:
    """Rebuild from trusted exception metadata; never copy content-bearing fields."""
    exc_info = hint.get("exc_info")
    if not exc_info or not isinstance(exc_info[1], Exception):
        return None
    error = exc_info[1]
    if type(error).__name__ == "CancelledError" and type(error).__module__ in {
        "asyncio.exceptions",
        "concurrent.futures._base",
    }:
        return None
    # Expected HTTP denials/validation failures are normal product outcomes.
    status = getattr(error, "status_code", None)
    if isinstance(status, int) and status < 500:
        return None
    name = type(error).__name__
    kind = name if type(error).__module__ == "builtins" and name in _ERROR_TYPES else "ApplicationError"
    frames: list[dict[str, Any]] = []
    traceback = exc_info[2]
    while traceback is not None:
        filename = Path(traceback.tb_frame.f_code.co_filename)
        try:
            relative = filename.resolve().relative_to(_CODE_ROOT)
        except (ValueError, OSError):
            pass
        else:
            if filename.suffix == ".py" and filename.is_file():
                frames.append({"filename": relative.as_posix(), "lineno": traceback.tb_lineno})
        traceback = traceback.tb_next
    environment = os.environ.get("SENTRY_ENVIRONMENT", "production")
    release = os.environ.get("SENTRY_RELEASE", os.environ.get("RENDER_GIT_COMMIT", ""))
    clean: dict[str, Any] = {
        "platform": "python",
        "level": "error",
        "environment": environment if environment in _ENVIRONMENTS else "unknown",
        "tags": {"component": component},
        "exception": {
            "values": [
                {
                    "type": kind,
                    "value": "Application error; private details removed",
                    "stacktrace": {"frames": frames[-50:]},
                }
            ]
        },
    }
    if re.fullmatch(r"[a-f0-9]{32}", event.get("event_id", "")):
        clean["event_id"] = event["event_id"]
    if re.fullmatch(r"[a-f0-9]{7,40}", release):
        clean["release"] = release
    return cast("Event", clean)


def init_sentry(
    component: str,
    *,
    api: bool = False,
    transport: Transport | None = None,
) -> bool:
    """Return readiness without making monitoring a dependency of application startup."""
    if os.environ.get("SENTRY_ENABLED", "").lower() != "true":
        return False
    dsn = os.environ.get("SENTRY_DSN", "")
    if not _valid_dsn(dsn):
        logging.getLogger(__name__).warning("Sentry disabled: missing or invalid DSN")
        return False
    integrations: list[Any] = [
        DedupeIntegration(),
        AtexitIntegration(),
        ExcepthookIntegration(),
        ThreadingIntegration(),
        LoggingIntegration(level=None, event_level=logging.ERROR),
    ]
    if api:
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        integrations.extend([FastApiIntegration(), StarletteIntegration()])

    def before_send(event: Event, hint: Hint) -> Event | None:
        hint["attachments"] = []
        with suppress(Exception):
            return _private_event(event, hint, component=component)
        return None

    with suppress(Exception):
        sentry_sdk.init(
            dsn=dsn,
            transport=transport,
            default_integrations=False,
            auto_enabling_integrations=False,
            integrations=integrations,
            before_send=before_send,
            before_send_log=lambda log, hint: None,
            before_send_metric=lambda metric, hint: None,
            before_send_transaction=lambda event, hint: None,
            data_collection={
                "user_info": False,
                "http_bodies": [],
                "stack_frame_variables": False,
                "frame_context_lines": 0,
                "gen_ai": {"inputs": False, "outputs": False},
                "cookies": {"mode": "off"},
                "http_headers": {"request": {"mode": "off"}},
                "url_query_params": {"mode": "off"},
                "database_query_data": False,
                "queues": False,
            },
            include_local_variables=False,
            max_request_body_size="never",
            max_breadcrumbs=0,
            traces_sample_rate=0,
            profiles_sample_rate=0,
            auto_session_tracking=False,
            send_client_reports=False,
            enable_logs=False,
            shutdown_timeout=0.2,
        )
        return True
    logging.getLogger(__name__).warning("Sentry disabled: initialization failed")
    return False


def capture_error(error: Exception) -> None:
    """Report a terminal caught failure without exposing it in application logs."""
    with suppress(Exception):
        sentry_sdk.capture_exception(error)
