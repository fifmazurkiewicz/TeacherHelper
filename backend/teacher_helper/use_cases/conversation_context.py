from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from teacher_helper.config import Settings, get_settings
from teacher_helper.infrastructure.db.llm_usage import record_llm_usage_event
from teacher_helper.infrastructure.db.models import ConversationORM, MessageORM
from teacher_helper.use_cases.ports import LlmClientPort

logger = logging.getLogger(__name__)

CONTEXT_KEY = "context"

SUMMARY_SYSTEM = (
    "Jesteś asystentem archiwizującym rozmowę nauczyciela z aplikacją TeacherHelper.\n"
    "Po polsku, zwięźle zaktualizuj podsumowanie rozmowy: ustalenia, wygenerowane materiały i pliki "
    "(tytuły), otwarte pytania, aktualny temat i zadania. Nie witaj się. "
    "Nie kopiuj dosłownie całego nowego fragmentu — syntetyzuj. "
    "Dopuszczalne krótkie listy punktowane; bez rozbudowanych nagłówków Markdown."
)


def messages_to_history_pairs(
    messages: list[MessageORM],
    message_pair_for_llm: Callable[[MessageORM], tuple[str, str]],
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in messages:
        if m.role not in ("user", "assistant"):
            continue
        out.append(message_pair_for_llm(m))
    return out


def _estimate_chars(pairs: list[tuple[str, str]]) -> int:
    return sum(len(content or "") for _, content in pairs)


def _merge_conv_extra(conv: ConversationORM, context_blob: dict[str, Any]) -> None:
    base: dict[str, Any] = dict(conv.extra) if isinstance(conv.extra, dict) else {}
    base[CONTEXT_KEY] = context_blob
    conv.extra = base


def _get_context_blob(conv: ConversationORM) -> dict[str, Any]:
    ex = conv.extra
    if not isinstance(ex, dict):
        return {}
    ctx = ex.get(CONTEXT_KEY)
    return dict(ctx) if isinstance(ctx, dict) else {}


def _format_chunk_for_summary(pairs: list[tuple[str, str]], start_idx: int, end_idx: int) -> str:
    lines: list[str] = []
    for i in range(start_idx, end_idx):
        role, content = pairs[i]
        label = "Użytkownik" if role == "user" else "Asystent"
        text = (content or "").strip()
        if len(text) > 12000:
            text = text[:12000] + "\n[… skrócono …]"
        lines.append(f"{label}: {text}")
    return "\n\n".join(lines)


def _summary_user_prompt(
    prev_summary: str,
    chunk: str,
    prev_covers: int,
    head_count: int,
) -> str:
    return (
        f"Dotychczasowe podsumowanie (obowiązuje dla wiadomości 0–{prev_covers}):\n"
        f"{prev_summary or '(brak — pierwsze podsumowanie)'}\n\n"
        f"Nowy fragment do włączenia (wiadomości {prev_covers}–{head_count}, role oznaczone):\n"
        f"{chunk}\n\n"
        "Zwróć wyłącznie zaktualizowane pełne podsumowanie całej rozmowy od początku do końca "
        f"objętego wiadomościami 0–{head_count}."
    )


def _cap_with_optional_prefix(
    pairs: list[tuple[str, str]],
    max_messages: int,
    *,
    prefix_messages: int,
) -> list[tuple[str, str]]:
    if max_messages <= 0 or len(pairs) <= max_messages:
        return pairs
    if prefix_messages <= 0:
        return pairs[-max_messages:]
    prefix = pairs[:prefix_messages]
    rest = pairs[prefix_messages:]
    budget = max_messages - len(prefix)
    if budget <= 0:
        return prefix[:max_messages]
    return prefix + rest[-budget:]


def cap_orchestrator_history(
    pairs: list[tuple[str, str]],
    *,
    settings: Settings | None = None,
    summary_prefix_messages: int = 0,
) -> list[tuple[str, str]]:
    s = settings or get_settings()
    cap = s.chat_orchestrator_max_messages
    return _cap_with_optional_prefix(pairs, cap, prefix_messages=summary_prefix_messages)


async def build_history_with_rolling_summary(
    session: AsyncSession,
    *,
    user_id: UUID,
    conv: ConversationORM,
    prior_msgs: list[MessageORM],
    message_pair_for_llm: Callable[[MessageORM], tuple[str, str]],
    summary_llm: LlmClientPort,
    settings: Settings | None = None,
    dry_run: bool = False,
) -> list[tuple[str, str]]:
    s = settings or get_settings()
    pairs = messages_to_history_pairs(prior_msgs, message_pair_for_llm)

    if not s.chat_summary_enabled or not pairs:
        return cap_orchestrator_history(pairs, settings=s, summary_prefix_messages=0)

    default_tail = min(len(pairs), max(2, s.chat_summary_recent_turns * 2))
    tail_msg_count = default_tail
    total_chars = _estimate_chars(pairs)
    long_thread = len(pairs) > default_tail
    over_chars = total_chars > s.chat_context_max_chars
    if not long_thread and not over_chars:
        return cap_orchestrator_history(pairs, settings=s, summary_prefix_messages=0)

    if over_chars and len(pairs) >= 2:
        tail_msg_count = max(1, min(tail_msg_count // 2, len(pairs) - 1))

    head_count = len(pairs) - tail_msg_count
    if head_count <= 0:
        return cap_orchestrator_history(pairs, settings=s, summary_prefix_messages=0)

    tail_pairs = pairs[-tail_msg_count:]
    ctx = _get_context_blob(conv)
    prev_summary = (ctx.get("summary") or "").strip()
    prev_covers = int(ctx.get("covers_count") or 0)

    if prev_covers > head_count:
        prev_covers = 0
        prev_summary = ""

    needs_llm = head_count > prev_covers or not prev_summary
    summary_text = prev_summary

    if needs_llm:
        if dry_run:
            summary_text = prev_summary or "[Dry-run] Podsumowanie kontekstu — wywołanie LLM pominięte."
            new_covers = head_count
            blob = {
                "summary": summary_text,
                "covers_count": new_covers,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            _merge_conv_extra(conv, blob)
        else:
            chunk = _format_chunk_for_summary(pairs, prev_covers, head_count)
            user_prompt = _summary_user_prompt(prev_summary, chunk, prev_covers, head_count)
            comp = await summary_llm.complete(SUMMARY_SYSTEM, user_prompt)
            summary_text = (comp.text or "").strip() or prev_summary
            new_covers = head_count
            blob = {
                "summary": summary_text,
                "covers_count": new_covers,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            _merge_conv_extra(conv, blob)
            await record_llm_usage_event(
                session,
                user_id=user_id,
                call_kind="conversation_summary",
                module_name=None,
                completion=comp,
                system_text=SUMMARY_SYSTEM,
                user_text=user_prompt,
                dry_run=dry_run,
            )
        logger.info(
            "conversation context: folded head=%d tail=%d dry_run=%s",
            head_count,
            tail_msg_count,
            dry_run,
        )
    else:
        logger.debug(
            "conversation context: reuse summary covers=%d head=%d tail=%d",
            prev_covers,
            head_count,
            tail_msg_count,
        )

    prefix = (
        "[Skrót wcześniejszej rozmowy — pełna treść pozostaje w archiwum czatu. "
        f"W kontekście modelu zastąpiono {head_count} wcześniejszych wiadomości poniższym podsumowaniem.]\n\n"
    )
    combined: list[tuple[str, str]] = [("user", prefix + summary_text)] + tail_pairs
    return cap_orchestrator_history(combined, settings=s, summary_prefix_messages=1)
