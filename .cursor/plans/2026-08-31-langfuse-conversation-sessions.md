# Plan: Langfuse Sessions per rozmowa (Faza A)

**Data:** 2026-08-31  
**Spec:** `docs/superpowers/specs/2026-08-31-langfuse-conversation-sessions-design.md`

## Decyzje

- `session_id = str(conversation_id)` w Langfuse
- Metadata: `conversation_id`, `project_id`, `job_id`
- Tylko ścieżka czatu + podsumowanie rozmowy; poza czatem bez sesji

## Zadania

- [x] `LangfuseTraceContext` + rozszerzenie `llm_usage.py`
- [x] Przekazanie kontekstu: `chat_job_runner`, orchestrator, `conversation_context`
- [x] Informacja dla userów (Assistant + Profil)
- [x] Dokumentacja + testy
- [x] Push na main
