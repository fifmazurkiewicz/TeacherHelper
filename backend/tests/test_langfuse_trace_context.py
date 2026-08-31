from __future__ import annotations

from uuid import uuid4

from teacher_helper.infrastructure.db.llm_usage import LangfuseTraceContext


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
