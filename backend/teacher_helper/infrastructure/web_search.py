"""Wyszukiwanie w internecie dla narzędzia LLM (Tavily Search API)."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from teacher_helper.config import get_settings

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


@dataclass(frozen=True)
class WebSearchHit:
    title: str
    url: str
    snippet: str


def _truncate(s: str, max_len: int) -> str:
    t = (s or "").strip().replace("\r\n", "\n").replace("\r", "\n")
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


async def run_web_search(query: str) -> tuple[list[WebSearchHit], str | None]:
    """
    Zwraca listę trafień oraz opcjonalny komunikat błędu dla użytkownika (np. brak klucza API).
    Przy błędzie HTTP zwraca pustą listę i komunikat.
    """
    q = (query or "").strip()
    if not q:
        return [], "Puste zapytanie do wyszukiwarki."

    s = get_settings()
    key = (getattr(s, "tavily_api_key", None) or "").strip()
    if not key:
        return [], (
            "Wyszukiwanie w internecie jest wyłączone: ustaw **TAVILY_API_KEY** w pliku `.env` "
            "(klucz z https://tavily.com)."
        )

    max_results = min(max(1, int(getattr(s, "web_search_max_results", 5) or 5)), 15)
    payload = {
        "api_key": key,
        "query": q,
        "search_depth": "basic",
        "include_answer": False,
        "max_results": max_results,
    }
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.post(TAVILY_SEARCH_URL, json=payload)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("Tavily HTTP %s: %s", exc.response.status_code, exc.response.text[:300])
        return [], f"Wyszukiwanie w internecie nie powiodło się (HTTP {exc.response.status_code})."
    except httpx.RequestError as exc:
        logger.warning("Tavily request error: %s", exc)
        return [], "Nie udało się połączyć z usługą wyszukiwania. Spróbuj ponownie później."

    raw_results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(raw_results, list):
        return [], "Nieoczekiwana odpowiedź wyszukiwarki."

    hits: list[WebSearchHit] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or url or "Bez tytułu").strip()
        body = str(item.get("content") or item.get("snippet") or "").strip()
        if not url and not body:
            continue
        hits.append(
            WebSearchHit(
                title=title,
                url=url,
                snippet=_truncate(body, 480),
            )
        )
    return hits, None


def format_hits_for_llm(query: str, hits: list[WebSearchHit]) -> str:
    """Blok tekstu do dynamicznego kontekstu modułu / odpowiedzi pomocniczej."""
    lines = [f"=== Wyniki wyszukiwania w internecie (zapytanie: {query.strip()}) ===", ""]
    for i, h in enumerate(hits, start=1):
        lines.append(f"[{i}] {h.title}")
        if h.url:
            lines.append(f" URL: {h.url}")
        lines.append(f"    {h.snippet}")
        lines.append("")
    return "\n".join(lines).rstrip()
