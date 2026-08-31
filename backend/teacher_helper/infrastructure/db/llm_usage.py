from __future__ import annotations

import asyncio
import json
import logging
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from teacher_helper.config import get_settings
from teacher_helper.infrastructure.db.models import LlmUsageLogORM
from teacher_helper.use_cases.ports import LlmCompletion

logger = logging.getLogger(__name__)

_langfuse_singleton: Any = None


@dataclass(frozen=True)
class LangfuseTraceContext:
    """Grupowanie obserwacji Langfuse w jednej sesji rozmowy."""

    conversation_id: UUID | None = None
    project_id: UUID | None = None
    job_id: UUID | None = None

    def session_id(self) -> str | None:
        if self.conversation_id is not None:
            return str(self.conversation_id)
        return None

    def metadata(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if self.conversation_id is not None:
            out["conversation_id"] = str(self.conversation_id)
        if self.project_id is not None:
            out["project_id"] = str(self.project_id)
        if self.job_id is not None:
            out["job_id"] = str(self.job_id)
        return out


def _merge_langfuse_metadata(
    base: dict[str, Any] | None,
    trace_context: LangfuseTraceContext | None,
) -> dict[str, Any]:
    out: dict[str, Any] = dict(base or {})
    if trace_context is not None:
        out.update(trace_context.metadata())
    return out


def _langfuse_client() -> Any | None:
    """Singleton Langfuse SDK v3 (OpenTelemetry)."""
    global _langfuse_singleton
    s = get_settings()
    if not s.langfuse_public_key or not s.langfuse_secret_key:
        return None
    if _langfuse_singleton is None:
        from langfuse import Langfuse

        _langfuse_singleton = Langfuse(
            public_key=s.langfuse_public_key,
            secret_key=s.langfuse_secret_key,
            base_url=s.langfuse_host.rstrip("/"),
            environment="production",
        )
    return _langfuse_singleton


def _langfuse_attr_context(
    user_id: UUID | None,
    trace_context: LangfuseTraceContext | None,
) -> AbstractContextManager[Any]:
    from langfuse import propagate_attributes

    uid = str(user_id) if user_id else None
    sid = trace_context.session_id() if trace_context else None
    if uid or sid:
        return propagate_attributes(user_id=uid, session_id=sid)
    return nullcontext()


def _usage_details_from_tokens(usage: dict[str, int] | None) -> dict[str, int] | None:
    if not usage:
        return None
    out: dict[str, int] = {}
    if usage.get("prompt_tokens") is not None:
        out["input"] = int(usage["prompt_tokens"])
    if usage.get("completion_tokens") is not None:
        out["output"] = int(usage["completion_tokens"])
    if usage.get("total_tokens") is not None:
        out["total"] = int(usage["total_tokens"])
    return out or None


def _completion_usage_details(completion: LlmCompletion) -> dict[str, int] | None:
    out: dict[str, int] = {}
    if completion.prompt_tokens is not None:
        out["input"] = completion.prompt_tokens
    if completion.completion_tokens is not None:
        out["output"] = completion.completion_tokens
    tt = completion.resolved_total_tokens()
    if tt is not None:
        out["total"] = tt
    return out or None


def langfuse_auth_check_sync() -> bool:
    lf = _langfuse_client()
    if lf is None:
        return False
    try:
        return bool(lf.auth_check())
    except Exception:
        logger.exception("Langfuse: auth_check nie powiódł się")
        return False


def send_langfuse_test_event_sync() -> dict[str, Any]:
    lf = _langfuse_client()
    if lf is None:
        return {"ok": False, "reason": "missing_keys"}
    try:
        with lf.start_as_current_observation(as_type="span", name="teacherhelper-admin-test") as span:
            span.update(
                input={"source": "admin_test"},
                output={"status": "ok", "service": "TeacherHelper"},
            )
        lf.flush()
        return {"ok": True, "auth_check": bool(lf.auth_check())}
    except Exception as exc:
        logger.exception("Langfuse: test event nie powiódł się")
        return {"ok": False, "reason": str(exc)[:300]}


def _to_decimal_usd(value: float | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return None


def cost_from_openrouter_response(data: dict[str, Any]) -> float | None:
    """Koszt w USD z odpowiedzi OpenRouter (pole ``usage.cost``)."""
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    for key in ("cost", "total_cost"):
        raw = usage.get(key)
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
    return None


def usage_from_openrouter_chat_response(data: dict[str, Any]) -> dict[str, int] | None:
    """Mapuje pole ``usage`` z odpowiedzi chat/completions (OpenRouter / OpenAI)."""
    raw = data.get("usage")
    if not isinstance(raw, dict):
        return None
    out: dict[str, int] = {}
    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        v = raw.get(k)
        if isinstance(v, int):
            out[k] = v
    return out or None


def usage_from_embeddings_response(data: dict[str, Any]) -> dict[str, int] | None:
    raw = data.get("usage")
    if not isinstance(raw, dict):
        return None
    out: dict[str, int] = {}
    for k in ("prompt_tokens", "total_tokens"):
        v = raw.get(k)
        if isinstance(v, int):
            out[k] = v
    return out or None


async def record_usage_log(
    session: AsyncSession,
    *,
    user_id: UUID | None,
    provider: str,
    model: str,
    call_kind: str,
    module_name: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    cost_usd: float | Decimal | None = None,
    dry_run: bool = False,
) -> None:
    row = LlmUsageLogORM(
        id=uuid4(),
        user_id=user_id,
        provider=provider[:64],
        model=(model or "unknown")[:256],
        call_kind=call_kind[:64],
        module_name=(module_name[:64] if module_name else None),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=_to_decimal_usd(cost_usd),
        dry_run=dry_run,
    )
    session.add(row)
    await session.flush()


def record_langfuse_model_call_sync(
    *,
    observation_name: str,
    model: str,
    provider: str,
    input_data: Any,
    output_text: str,
    user_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
    usage: dict[str, int] | None = None,
    cost_usd: float | None = None,
    trace_context: LangfuseTraceContext | None = None,
) -> None:
    """Langfuse dla wywołań spoza standardowego ``LlmCompletion`` (obrazy, embeddingi, audio, KIE)."""
    lf = _langfuse_client()
    if lf is None:
        return
    try:
        meta = _merge_langfuse_metadata({"provider": provider, **(metadata or {})}, trace_context)
        if cost_usd is not None:
            meta["cost_usd"] = cost_usd
        if isinstance(input_data, str):
            inp: Any = input_data[:12000]
        else:
            try:
                inp = json.dumps(input_data, ensure_ascii=False)[:12000]
            except (TypeError, ValueError):
                inp = str(input_data)[:12000]
        with _langfuse_attr_context(user_id, trace_context):
            with lf.start_as_current_observation(
                as_type="generation",
                name=observation_name,
                model=model,
                input=inp,
            ) as gen:
                gen.update(
                    output=output_text[:32000],
                    metadata=meta,
                    usage_details=_usage_details_from_tokens(usage),
                )
        lf.flush()
    except Exception:
        logger.exception("Langfuse: zapis %s nie powiódł się", observation_name)


def _emit_langfuse_sync(
    *,
    observation_name: str,
    completion: LlmCompletion,
    call_kind: str,
    module_name: str | None,
    user_id: UUID | None,
    system_text: str,
    user_text: str,
    output_text: str,
    trace_context: LangfuseTraceContext | None = None,
) -> None:
    lf = _langfuse_client()
    if lf is None:
        return
    try:
        meta = _merge_langfuse_metadata(
            {
                "call_kind": call_kind,
                "module_name": module_name or "",
                "provider": completion.provider,
                "cost_usd": completion.cost_usd,
            },
            trace_context,
        )
        with _langfuse_attr_context(user_id, trace_context):
            with lf.start_as_current_observation(
                as_type="generation",
                name=observation_name,
                model=completion.model,
                input=[
                    {"role": "system", "content": system_text[:12000]},
                    {"role": "user", "content": user_text[:12000]},
                ],
            ) as gen:
                gen.update(
                    output=(output_text or "")[:32000],
                    metadata=meta,
                    usage_details=_completion_usage_details(completion),
                )
        lf.flush()
    except Exception:
        logger.exception("Langfuse: zapis obserwacji nie powiódł się")


async def record_llm_usage_event(
    session: AsyncSession,
    *,
    user_id: UUID | None,
    call_kind: str,
    module_name: str | None,
    completion: LlmCompletion,
    system_text: str,
    user_text: str,
    dry_run: bool = False,
    trace_context: LangfuseTraceContext | None = None,
) -> None:
    total = completion.resolved_total_tokens()
    await record_usage_log(
        session,
        user_id=user_id,
        provider=completion.provider,
        model=completion.model,
        call_kind=call_kind,
        module_name=module_name,
        prompt_tokens=completion.prompt_tokens,
        completion_tokens=completion.completion_tokens,
        total_tokens=total,
        cost_usd=completion.cost_usd,
        dry_run=dry_run,
    )
    if dry_run:
        return
    await asyncio.to_thread(
        _emit_langfuse_sync,
        observation_name=f"llm:{call_kind}" + (f":{module_name}" if module_name else ""),
        completion=completion,
        call_kind=call_kind,
        module_name=module_name,
        user_id=user_id,
        system_text=system_text,
        user_text=user_text,
        output_text=completion.text,
        trace_context=trace_context,
    )
