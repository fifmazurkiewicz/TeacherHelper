from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Update
from sqlalchemy.sql.selectable import Select

from teacher_helper.infrastructure.jobs import (
    STALE_RUNNING_JOB_MESSAGE,
    JobStatus,
    claim_job_running,
    conversation_has_active_chat_job,
    reap_stale_running_jobs,
)


class _ExecResult:
    def __init__(self, *, rowcount: int = 0, scalar=None) -> None:
        self.rowcount = rowcount
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar


class _FakeSession:
    def __init__(self, *, execute_result=None, scalar_result=None) -> None:
        self.statements: list = []
        self._execute_result = execute_result or _ExecResult()
        self._scalar_result = scalar_result

    async def execute(self, stmt):
        self.statements.append(stmt)
        return self._execute_result

    async def scalar(self, stmt):
        self.statements.append(stmt)
        return self._scalar_result


def _bound_values(stmt) -> list:
    compiled = stmt.compile(dialect=postgresql.dialect())
    values: list = []
    for value in compiled.params.values():
        if isinstance(value, (list, tuple, set)):
            values.extend(value)
        else:
            values.append(value)
    return values


async def test_claim_job_running_updates_only_pending() -> None:
    job_id = uuid4()
    session = _FakeSession(execute_result=_ExecResult(rowcount=1, scalar=job_id))
    claimed = await claim_job_running(session, job_id)
    assert claimed is True
    assert len(session.statements) == 1
    stmt = session.statements[0]
    assert isinstance(stmt, Update)
    values = _bound_values(stmt)
    assert JobStatus.pending.value in values
    assert JobStatus.running.value in values


async def test_claim_job_running_returns_false_when_not_pending() -> None:
    session = _FakeSession(execute_result=_ExecResult(rowcount=0, scalar=None))
    claimed = await claim_job_running(session, uuid4())
    assert claimed is False


async def test_conversation_has_active_chat_job_filters_pending_and_running() -> None:
    conv_id = uuid4()
    existing = SimpleNamespace(id=uuid4(), status=JobStatus.pending.value)
    session = _FakeSession(scalar_result=existing)
    found = await conversation_has_active_chat_job(session, conv_id)
    assert found is existing
    stmt = session.statements[0]
    assert isinstance(stmt, Select)
    values = _bound_values(stmt)
    assert JobStatus.pending.value in values
    assert JobStatus.running.value in values
    assert "chat" in values


async def test_conversation_has_active_chat_job_none_when_idle() -> None:
    session = _FakeSession(scalar_result=None)
    assert await conversation_has_active_chat_job(session, uuid4()) is None


async def test_reap_stale_running_jobs_marks_error() -> None:
    session = _FakeSession(execute_result=_ExecResult(rowcount=2))
    n = await reap_stale_running_jobs(session, max_age_minutes=15)
    assert n == 2
    stmt = session.statements[0]
    assert isinstance(stmt, Update)
    values = _bound_values(stmt)
    assert JobStatus.running.value in values
    assert JobStatus.error.value in values
    assert STALE_RUNNING_JOB_MESSAGE in values
    assert "utkn" in STALE_RUNNING_JOB_MESSAGE.lower() or "limit" in STALE_RUNNING_JOB_MESSAGE.lower()


def test_stale_cutoff_is_fifteen_minutes_by_default() -> None:
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    cutoff = now - timedelta(minutes=15)
    assert cutoff == datetime(2026, 9, 6, 11, 45, tzinfo=timezone.utc)
