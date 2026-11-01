"""Inspect real SDK envelopes using a transport that cannot reach a network."""

import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest
import sentry_sdk
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport

from teacher_helper.monitoring import init_sentry

DSN = "https://0123456789abcdef0123456789abcdef@o1.ingest.de.sentry.io/123"
PRIVATE = "PRIVATE-CONTENT-123: patient audio prompt token /Users/Private/file.txt"


class MemoryTransport(Transport):
    def __init__(self) -> None:
        super().__init__({"dsn": DSN})
        self.envelopes: list[Envelope] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        self.envelopes.append(envelope)


@pytest.fixture(autouse=True)
def clean_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    old_client = sentry_sdk.get_client()
    monkeypatch.setenv("SENTRY_ENABLED", "true")
    monkeypatch.setenv("SENTRY_DSN", DSN)
    yield
    sentry_sdk.get_client().close()
    sentry_sdk.get_global_scope().set_client(old_client)


@pytest.mark.parametrize(
    "enabled,dsn",
    [("false", DSN), ("", DSN), ("true", ""), ("true", "invalid"), ("true", "https://private@example.org/1")],
)
def test_missing_disabled_or_invalid_configuration_sends_nothing(
    monkeypatch: pytest.MonkeyPatch, enabled: str, dsn: str
) -> None:
    transport = MemoryTransport()
    monkeypatch.setenv("SENTRY_ENABLED", enabled)
    monkeypatch.setenv("SENTRY_DSN", dsn)
    assert init_sentry("teacherhelper-api", api=True, transport=transport) is False
    assert transport.envelopes == []


def test_api_failure_reports_once_without_user_content() -> None:
    transport = MemoryTransport()
    assert init_sentry("teacherhelper-api", api=True, transport=transport)
    app = FastAPI()

    @app.post("/private/{record}")
    def fail(record: str, payload: dict[str, Any]) -> None:
        sentry_sdk.set_user({"email": PRIVATE})
        sentry_sdk.set_context("private", {"nested": {"content": PRIVATE}})
        sentry_sdk.set_extra("private", PRIVATE)
        sentry_sdk.add_breadcrumb(message=PRIVATE)
        sentry_sdk.add_attachment(bytes=PRIVATE.encode(), filename="private.txt")
        raise RuntimeError(PRIVATE)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/private/owner-id", json={"prompt": PRIVATE}, headers={"Authorization": PRIVATE, "Cookie": PRIVATE}
        )
    assert response.status_code == 500
    assert len(transport.envelopes) == 1
    assert [item.type for item in transport.envelopes[0].items] == ["event"]
    raw = transport.envelopes[0].serialize().decode()
    assert PRIVATE not in raw
    assert "owner-id" not in raw
    assert "/Users/" not in raw
    event = transport.envelopes[0].get_event()
    assert event["exception"]["values"][0]["type"] == "RuntimeError"
    assert event["tags"] == {"component": "teacherhelper-api"}
    assert not {"request", "user", "extra", "contexts", "breadcrumbs", "transaction"} & event.keys()


def test_caught_terminal_error_reports_once_and_messages_are_dropped() -> None:
    transport = MemoryTransport()
    assert init_sentry("teacherhelper-api", transport=transport)
    try:
        raise ValueError(PRIVATE)
    except ValueError as error:
        logging.getLogger(__name__).exception(PRIVATE)
        sentry_sdk.capture_exception(error)
    sentry_sdk.capture_message(PRIVATE)
    assert len(transport.envelopes) == 1
    assert PRIVATE not in json.dumps(transport.envelopes[0].get_event())


def test_expected_denial_is_not_an_application_failure() -> None:
    transport = MemoryTransport()
    assert init_sentry("teacherhelper-api", api=True, transport=transport)
    sentry_sdk.capture_exception(HTTPException(status_code=403, detail=PRIVATE))
    assert transport.envelopes == []


def test_failed_initialization_does_not_prevent_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_init(**kwargs: object) -> None:
        raise OSError(PRIVATE)

    monkeypatch.setattr(sentry_sdk, "init", broken_init)
    assert init_sentry("teacherhelper-api", transport=MemoryTransport()) is False


def test_broken_transport_does_not_change_api_failure() -> None:
    class BrokenTransport(MemoryTransport):
        def capture_envelope(self, envelope: Envelope) -> None:
            raise OSError(PRIVATE)

    assert init_sentry("teacherhelper-api", api=True, transport=BrokenTransport())
    app = FastAPI()

    @app.get("/fail")
    def fail() -> None:
        raise RuntimeError(PRIVATE)

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/fail").status_code == 500


def test_non_error_products_never_deliver_private_data() -> None:
    transport = MemoryTransport()
    assert init_sentry("teacherhelper-api", transport=transport)
    sentry_sdk.metrics.count("private-metric", 1, attributes={"private": PRIVATE})
    sentry_sdk.logger.error(PRIVATE, attributes={"private": PRIVATE})
    with sentry_sdk.start_transaction(name=PRIVATE, sampled=True):
        pass
    sentry_sdk.flush(timeout=1)
    assert transport.envelopes == []
