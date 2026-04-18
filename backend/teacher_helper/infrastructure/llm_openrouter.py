from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from teacher_helper.use_cases.ports import LlmCompletion, ToolCall, ToolDefinition

logger = logging.getLogger(__name__)


class OpenRouterLlmClient:
    """Klient LLM przez OpenRouter (API zgodne z OpenAI Chat Completions + tool calling)."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str = "https://openrouter.ai/api/v1",
        http_referer: str | None = None,
        app_title: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base = base_url.rstrip("/")
        self._referer = http_referer
        self._title = app_title

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self._referer:
            h["HTTP-Referer"] = self._referer
        if self._title:
            h["X-Title"] = self._title
        return h

    @staticmethod
    def _message_text(content: object) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for p in content:
                if isinstance(p, dict):
                    if p.get("type") == "text" and "text" in p:
                        parts.append(str(p["text"]))
                    elif "text" in p:
                        parts.append(str(p["text"]))
                elif isinstance(p, str):
                    parts.append(p)
            return "".join(parts)
        return str(content)

    async def complete(self, system: str, user: str) -> LlmCompletion:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return await self._call(messages)

    async def complete_with_tools(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition],
    ) -> LlmCompletion:
        full_messages = [{"role": "system", "content": system}, *messages]
        return await self._call(full_messages, tools=tools)

    async def _call(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
    ) -> LlmCompletion:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        url = f"{self._base}/chat/completions"
        logger.debug("OpenRouter request: model=%s url=%s msgs=%d tools=%d",
                     self._model, url, len(messages), len(tools or []))
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(url, json=payload, headers=self._headers())
        logger.debug("OpenRouter response: status=%d content_length=%d", r.status_code, len(r.content))
        if r.is_error:
            detail = r.text[:800] if r.text else r.reason_phrase
            logger.error("OpenRouter HTTP error %d: %s", r.status_code, detail)
            raise RuntimeError(f"OpenRouter HTTP {r.status_code}: {detail}")

        data = r.json()
        choices = data.get("choices")
        if not choices:
            logger.error("OpenRouter: no choices in response, keys=%s", list(data.keys()))
            raise RuntimeError(f"OpenRouter: brak pola choices w odpowiedzi. Klucze: {list(data.keys())}")

        choice = choices[0]
        msg = choice.get("message") or {}
        text = self._message_text(msg.get("content"))
        finish = choice.get("finish_reason")

        parsed_tools: list[ToolCall] = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}
            parsed_tools.append(ToolCall(
                id=tc.get("id", ""),
                name=fn.get("name", ""),
                arguments=args,
            ))

        model_out = str(data.get("model") or self._model)
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        pt = usage.get("prompt_tokens")
        ct = usage.get("completion_tokens")
        tt = usage.get("total_tokens")
        return LlmCompletion(
            text=text,
            provider="openrouter",
            model=model_out,
            prompt_tokens=int(pt) if pt is not None else None,
            completion_tokens=int(ct) if ct is not None else None,
            total_tokens=int(tt) if tt is not None else None,
            tool_calls=parsed_tools,
            finish_reason=finish,
        )
