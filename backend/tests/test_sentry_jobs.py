"""Actual chat-job boundary keeps error persistence while monitoring fails safely."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from teacher_helper.adapters.http.schemas import ChatRequest
from teacher_helper.use_cases import chat_job_runner
from teacher_helper.use_cases.error_reporting import set_error_reporter


@pytest.mark.parametrize("reporter_fails", [False, True])
async def test_chat_job_persists_failure_even_if_reporter_fails(monkeypatch, reporter_fails):
    user_id, job_id, conversation_id = uuid4(), uuid4(), uuid4()
    session = AsyncMock()
    session.get.return_value = SimpleNamespace(id=conversation_id, user_id=user_id, project_id=None)
    session.scalars.return_value = MagicMock(all=lambda: [])
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(chat_job_runner, "async_session_factory", lambda: context)
    monkeypatch.setattr(
        chat_job_runner,
        "get_job",
        AsyncMock(return_value=SimpleNamespace(user_id=user_id, conversation_id=conversation_id)),
    )
    monkeypatch.setattr(chat_job_runner, "claim_job_running", AsyncMock(return_value=True))
    monkeypatch.setattr(chat_job_runner, "build_history_with_rolling_summary", AsyncMock(return_value=[]))
    provider_error = RuntimeError("synthetic-private-provider-payload")
    monkeypatch.setattr(chat_job_runner._orchestrator, "execute", AsyncMock(side_effect=provider_error))
    failed = AsyncMock()
    monkeypatch.setattr(chat_job_runner, "mark_job_error", failed)
    monkeypatch.setattr(chat_job_runner, "record_system_incident", AsyncMock())
    monkeypatch.setattr(chat_job_runner, "send_alert_webhook", AsyncMock())
    observed = []

    def report(error):
        observed.append(error)
        if reporter_fails:
            raise OSError("monitoring offline")

    try:
        set_error_reporter(report)
        await chat_job_runner.run_chat_job(job_id, user_id, ChatRequest(message="synthetic"))
        assert observed == [provider_error]
        failed.assert_awaited_once_with(session, job_id, str(provider_error))
        assert session.commit.await_count == 2
    finally:
        set_error_reporter(None)
