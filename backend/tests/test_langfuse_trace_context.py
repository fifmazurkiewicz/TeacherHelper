from __future__ import annotations

from uuid import uuid4

from teacher_helper.infrastructure.db.llm_usage import LangfuseTraceContext, _langfuse_trace_kwargs


def test_langfuse_trace_context_session_id() -> None:
    conv_id = uuid4()
    job_id = uuid4()
    project_id = uuid4()
    ctx = LangfuseTraceContext(conversation_id=conv_id, project_id=project_id, job_id=job_id)
    assert ctx.session_id() == str(conv_id)
    assert ctx.metadata() == {
        "conversation_id": str(conv_id),
        "project_id": str(project_id),
        "job_id": str(job_id),
    }


def test_langfuse_trace_kwargs_includes_session() -> None:
    conv_id = uuid4()
    user_id = uuid4()
    ctx = LangfuseTraceContext(conversation_id=conv_id)
    kw = _langfuse_trace_kwargs(
        user_id=user_id,
        trace_context=ctx,
        metadata={"call_kind": "orchestrator"},
    )
    assert kw["session_id"] == str(conv_id)
    assert kw["user_id"] == str(user_id)
    assert kw["metadata"]["conversation_id"] == str(conv_id)
    assert kw["metadata"]["call_kind"] == "orchestrator"


def test_langfuse_trace_kwargs_without_context() -> None:
    kw = _langfuse_trace_kwargs(user_id=None, trace_context=None, metadata=None)
    assert "session_id" not in kw
    assert kw["user_id"] is None
