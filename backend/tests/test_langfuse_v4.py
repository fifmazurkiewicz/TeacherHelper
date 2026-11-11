"""Real SDK integration without network access or application credentials."""

import json
from uuid import UUID, uuid4

import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from teacher_helper.infrastructure.db import llm_usage


@pytest.fixture
def exporter(monkeypatch):
    sink = InMemorySpanExporter()
    client = Langfuse(
        public_key=f"pk-synthetic-{uuid4()}",
        secret_key="sk-synthetic-test",
        base_url="https://langfuse.invalid",
        environment="test",
        tracer_provider=TracerProvider(),
        span_exporter=sink,
    )
    monkeypatch.setattr(llm_usage, "_langfuse_client", lambda: client)
    yield sink
    client.shutdown()


def test_generations_preserve_usage_and_isolate_conversations(exporter):
    for value in (1, 2, None):
        context = llm_usage.LangfuseTraceContext(conversation_id=UUID(int=value)) if value else None
        llm_usage.record_langfuse_model_call_sync(
            observation_name="synthetic-generation",
            model="synthetic-model",
            provider="synthetic",
            input_data="synthetic input",
            output_text="synthetic output",
            user_id=UUID(int=value + 10) if value else None,
            trace_context=context,
            usage={"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
        )
    spans = exporter.get_finished_spans()
    assert len(spans) == 3
    for span, value in zip(spans, (1, 2, None), strict=True):
        attrs = span.attributes
        assert attrs["langfuse.observation.type"] == "generation"
        assert attrs["langfuse.observation.model.name"] == "synthetic-model"
        if value:
            assert attrs["session.id"] == str(UUID(int=value))
            assert attrs["user.id"] == str(UUID(int=value + 10))
        else:
            assert "session.id" not in attrs
            assert "user.id" not in attrs
        assert json.loads(attrs["langfuse.observation.usage_details"]) == {"input": 12, "output": 3, "total": 15}


def test_missing_credentials_disable_telemetry(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        llm_usage,
        "get_settings",
        lambda: SimpleNamespace(
            langfuse_public_key=None,
            langfuse_secret_key=None,
        ),
    )
    assert llm_usage.send_langfuse_test_event_sync() == {"ok": False, "reason": "missing_keys"}
    assert llm_usage.langfuse_auth_check_sync() is False


def test_chat_completion_emits_generation_with_session(exporter):
    from teacher_helper.use_cases.ports import LlmCompletion

    llm_usage._emit_langfuse_sync(
        observation_name="llm:chat",
        completion=LlmCompletion(
            text="synthetic reply", provider="synthetic", model="synthetic-model", prompt_tokens=5, completion_tokens=2
        ),
        call_kind="chat",
        module_name=None,
        user_id=UUID(int=20),
        system_text="synthetic system",
        user_text="synthetic question",
        output_text="synthetic reply",
        trace_context=llm_usage.LangfuseTraceContext(conversation_id=UUID(int=30)),
    )
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    attrs = spans[0].attributes
    assert attrs["session.id"] == str(UUID(int=30))
    assert attrs["langfuse.observation.output"] == "synthetic reply"
    assert json.loads(attrs["langfuse.observation.usage_details"]) == {"input": 5, "output": 2, "total": 7}


def test_default_transport_uses_v4_ingestion(monkeypatch):
    from types import SimpleNamespace

    import requests
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

    requests_sent = []

    def send(session, request, **kwargs):
        requests_sent.append(request)
        response = requests.Response()
        response.status_code = 200
        response._content = b""
        return response

    monkeypatch.setattr(requests.Session, "send", send)
    monkeypatch.setattr(llm_usage, "_langfuse_singleton", None)
    monkeypatch.setattr(
        llm_usage,
        "get_settings",
        lambda: SimpleNamespace(
            langfuse_public_key=f"pk-synthetic-{uuid4()}",
            langfuse_secret_key="sk-synthetic-test",
            langfuse_host="https://langfuse.invalid",
        ),
    )
    try:
        llm_usage.record_langfuse_model_call_sync(
            observation_name="v4-transport-test",
            model="synthetic-model",
            provider="synthetic",
            input_data="synthetic input",
            output_text="synthetic output",
        )
        assert len(requests_sent) == 1
        request = requests_sent[0]
        assert request.url == "https://langfuse.invalid/api/public/otel/v1/traces"
        assert request.headers["x-langfuse-ingestion-version"] == "4"
        payload = ExportTraceServiceRequest.FromString(request.body)
        names = [
            span.name for resource in payload.resource_spans for scope in resource.scope_spans for span in scope.spans
        ]
        assert names == ["v4-transport-test"]
    finally:
        if llm_usage._langfuse_singleton is not None:
            llm_usage._langfuse_singleton.shutdown()
