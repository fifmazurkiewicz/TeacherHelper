# Langfuse Sessions per rozmowa (Faza A) — design

**Data:** 2026-08-31

## Cel

Administrator (i developer) widzi w Langfuse **jedną sesję = jedna rozmowa** (`conversation_id`) ze wszystkimi wywołaniami modelu z tej rozmowy (orchestrator, moduły, podsumowanie kontekstu). Użytkownicy są informowani o logowaniu wywołań LLM.

## Wymagania (Given / When / Then)

- **Given** włączone `LANGFUSE_*` i wywołanie czatu (nie `dry_run`)
- **When** orchestrator lub podsumowanie rozmowy wywołuje model
- **Then** trace Langfuse ma `session_id = conversation_id` i metadata: `conversation_id`, `project_id`, `job_id`

- **Given** `dry_run=true`
- **When** czat jest symulowany
- **Then** brak wysyłki do Langfuse (jak dotychczas)

- **Given** wywołanie LLM poza czatem (np. intent, embedding)
- **When** brak kontekstu rozmowy
- **Then** trace bez `session_id` (jak dotychczas)

- **Given** zalogowany nauczyciel
- **When** otwiera asystent lub profil
- **Then** widzi krótką informację o logowaniu wywołań LLM (limity, jakość) i opcjonalnym Langfuse Cloud

## API / kod

- `LangfuseTraceContext` w `llm_usage.py` — `conversation_id`, `project_id`, `job_id`
- `record_llm_usage_event`, `record_langfuse_model_call_sync` — opcjonalny `trace_context`
- `ChatOrchestratorUseCase.execute(..., trace_context=...)` z `chat_job_runner`
- `build_history_with_rolling_summary(..., trace_context=...)`

## UI

- `AssistantPage` — krótka informacja pod nagłówkiem / w stopce czatu
- `ProfilePage` — sekcja „Dane i monitoring”

## Decyzje

- **Źródło sesji:** `conversation_id` z Postgres (nie nowe ID).
- **llm_usage_log:** bez `conversation_id` w tej fazie (insight w Langfuse, nie w panelu admina).
