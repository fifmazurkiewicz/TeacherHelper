from __future__ import annotations

import asyncio
import logging
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from teacher_helper.config import get_settings
from teacher_helper.infrastructure.db.models import LlmUsageLogORM
from teacher_helper.use_cases.ports import LlmCompletion

logger = logging.getLogger(__name__)


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
            metadata={"provider": completion.provider, "call_kind": call_kind},
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
    row = LlmUsageLogORM(
        id=uuid4(),
        user_id=user_id,
        provider=completion.provider[:64],
        model=(completion.model or "unknown")[:256],
        call_kind=call_kind[:64],
        module_name=(module_name[:64] if module_name else None),
        prompt_tokens=completion.prompt_tokens,
        completion_tokens=completion.completion_tokens,
        total_tokens=total,
        dry_run=dry_run,
    )
    session.add(row)
    await session.flush()
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
