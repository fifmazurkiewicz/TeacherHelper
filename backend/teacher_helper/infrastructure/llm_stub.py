from __future__ import annotations

import json
from typing import Any

from teacher_helper.use_cases.ports import LlmCompletion, ToolCall, ToolDefinition


class StubLlmClient:
    """Symulacja LLM z obsługą tool calling — zwraca realistyczne tool calls lub tekst."""

    async def complete(self, system: str, user: str) -> LlmCompletion:
        u = user[:200].replace('"', "'")
        if "JSON" in system or "Asystent" in system or "asystent" in system.lower():
            has_history = "Historia rozmowy" in user
            if has_history:
                text = json.dumps(
                    {
                        "assistant_reply": f"[STUB] Rozumiem! Przygotowuję materiały na podstawie naszej rozmowy: \u201e{u[:100]}\u201d.",
                        "run_modules": ["scenario"],
                        "needs_clarification": False,
                        "clarification_question": None,
                    },
                    ensure_ascii=False,
                )
            else:
                text = json.dumps(
                    {
                        "assistant_reply": (
                            f"[STUB] Świetny pomysł! Chętnie pomogę: \u201e{u[:100]}\u201d. "
                            "Dla jakiej grupy wiekowej? Czy oprócz głównego materiału "
                            "przygotować też piosenkę lub grafikę?"
                        ),
                        "run_modules": [],
                        "needs_clarification": True,
                        "clarification_question": "Dla jakiej klasy / grupy wiekowej? Czy chcesz dodatkowe materiały (piosenka, grafika)?",
                    },
                    ensure_ascii=False,
                )
            return LlmCompletion(text=text, provider="stub", model="stub")

        return LlmCompletion(text=f"[STUB] {u}", provider="stub", model="stub")

    async def complete_with_tools(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition],
    ) -> LlmCompletion:
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = str(m.get("content", ""))[:200]
                break

        tool_names = [t.get("function", {}).get("name", "") for t in tools]

        has_history = len([m for m in messages if m.get("role") == "user"]) > 1

        if has_history and "generate_scenario" in tool_names:
            return LlmCompletion(
                text="Przygotowuję scenariusz na podstawie naszej rozmowy.",
                provider="stub",
                model="stub",
                tool_calls=[ToolCall(
                    id="stub_tc_1",
                    name="generate_scenario",
                    arguments={"topic": last_user[:100], "age_group": "klasy 4-6", "duration_minutes": 30},
                )],
                finish_reason="tool_calls",
            )

        if "ask_clarification" in tool_names:
            return LlmCompletion(
                text="",
                provider="stub",
                model="stub",
                tool_calls=[ToolCall(
                    id="stub_tc_0",
                    name="ask_clarification",
                    arguments={
                        "question": "Dla jakiej grupy wiekowej? Czy chcesz dodatkowe materiały (piosenkę, grafikę)?",
                        "suggestions": ["piosenka", "grafika", "plakat"],
                    },
                )],
                finish_reason="tool_calls",
            )

        return LlmCompletion(
            text=f"[STUB] Odpowiedź na: {last_user}",
            provider="stub",
            model="stub",
            finish_reason="stop",
        )
