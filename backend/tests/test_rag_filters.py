from __future__ import annotations

from uuid import uuid4

from teacher_helper.infrastructure.vector_search import apply_rag_sql_filters, rag_score_passes


def test_rag_score_passes_respects_min() -> None:
    assert rag_score_passes(0.40, 0.25) is True
    assert rag_score_passes(0.10, 0.25) is False
    assert rag_score_passes(0.10, None) is True


def test_apply_rag_sql_filters_includes_project_and_min_score() -> None:
    pid = uuid4()
    extra, params = apply_rag_sql_filters(project_id=pid, min_score=0.25, library_only=True)
    assert "fa.project_id" in extra
    assert "min_score" in extra
    assert "fa.topic_id IS NULL" in extra
    assert params["project_id"] == str(pid)
    assert params["min_score"] == 0.25


def test_apply_rag_sql_filters_topic_search_omits_library_only() -> None:
    tid = uuid4()
    extra, params = apply_rag_sql_filters(topic_id=tid, min_score=0.3, library_only=False)
    assert "fa.topic_id = CAST(:topic_id AS uuid)" in extra
    assert "IS NULL" not in extra
    assert params["topic_id"] == str(tid)
    assert "project_id" not in params
