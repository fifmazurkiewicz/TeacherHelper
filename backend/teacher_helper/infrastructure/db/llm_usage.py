from __future__ import annotations

import asyncio
import json
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from teacher_helper.config import get_settings
from teacher_helper.infrastructure.db.models import LlmUsageLogORM
from teacher_helper.use_cases.ports import LlmCompletion

logger = logging.getLogger(__name__)


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
) -> None:
    """Langfuse dla wywołań spoza standardowego ``LlmCompletion`` (obrazy, embeddingi, audio, KIE)."""
    s = get_settings()
    if not s.langfuse_public_key or not s.langfuse_secret_key:
        return
    try:
        from langfuse import Langfuse

        lf = Langfuse(
            public_key=s.langfuse_public_key,
            secret_key=s.langfuse_secret_key,
            host=s.langfuse_host.rstrip("/"),
        )
        meta = {"provider": provider, **(metadata or {})}
        if cost_usd is not None:
            meta["cost_usd"] = cost_usd
        trace = lf.trace(
            name="TeacherHelper",
            user_id=str(user_id) if user_id else None,
            metadata=meta,
        )
        if isinstance(input_data, str):
            inp: Any = input_data[:12000]
        else:
            try:
                inp = json.dumps(input_data, ensure_ascii=False)[:12000]
            except (TypeError, ValueError):
                inp = str(input_data)[:12000]
        gen = trace.generation(
            name=observation_name,
            model=model,
            input=inp,
            output=output_text[:32000],
            metadata=meta,
        )
        end_fn = getattr(gen, "end", None)
        if callable(end_fn):
            if usage:
                try:
                    end_fn(usage=usage)
                except TypeError:
                    end_fn(
                        usage={
                            "promptTokens": usage.get("prompt_tokens", 0),
                            "completionTokens": usage.get("completion_tokens", 0),
                            "totalTokens": usage.get("total_tokens", 0),
                        }
                    )
            else:
                end_fn()
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
) -> None:
    s = get_settings()
    if not s.langfuse_public_key or not s.langfuse_secret_key:
        return
    try:
        from langfuse import Langfuse

        lf = Langfuse(
            public_key=s.langfuse_public_key,
            secret_key=s.langfuse_secret_key,
            host=s.langfuse_host.rstrip("/"),
        )
        trace = lf.trace(
            name="TeacherHelper",
            user_id=str(user_id) if user_id else None,
            metadata={
                "call_kind": call_kind,
                "module_name": module_name or "",
                "provider": completion.provider,
                "cost_usd": completion.cost_usd,
            },
        )
        gen = trace.generation(
            name=observation_name,
            model=completion.model,
            input=[
                {"role": "system", "content": system_text[:12000]},
                {"role": "user", "content": user_text[:12000]},
            ],
            output=output_text[:32000],
            metadata={
                "provider": completion.provider,
                "call_kind": call_kind,
                "cost_usd": completion.cost_usd,
            },
        )
        usage: dict[str, int] = {}
        if completion.prompt_tokens is not None:
            usage["prompt_tokens"] = completion.prompt_tokens
        if completion.completion_tokens is not None:
            usage["completion_tokens"] = completion.completion_tokens
        tt = completion.resolved_total_tokens()
        if tt is not None:
            usage["total_tokens"] = tt
        end_fn = getattr(gen, "end", None)
        if callable(end_fn):
            if usage:
                try:
                    end_fn(usage=usage)
                except TypeError:
                    end_fn(
                        usage={
                            "promptTokens": usage.get("prompt_tokens", 0),
                            "completionTokens": usage.get("completion_tokens", 0),
                            "totalTokens": usage.get("total_tokens", 0),
                        }
                    )
            else:
                end_fn()
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
    )
