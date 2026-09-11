from __future__ import annotations

from types import SimpleNamespace

import pytest

from teacher_helper.infrastructure import web_search


@pytest.mark.asyncio
async def test_disabled_web_search_does_not_call_http(monkeypatch) -> None:
    monkeypatch.setattr(
        web_search,
        "get_settings",
        lambda: SimpleNamespace(
            web_search_enabled=False,
            tavily_api_key="configured-but-disabled",
            web_search_max_results=5,
        ),
    )

    class UnexpectedClient:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("HTTP client must not be created while web search is disabled")

    monkeypatch.setattr(web_search.httpx, "AsyncClient", UnexpectedClient)

    hits, error = await web_search.run_web_search("układ słoneczny")
    assert hits == []
    assert error == "Wyszukiwanie w internecie jest obecnie wyłączone."
