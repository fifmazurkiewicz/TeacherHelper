# TeacherHelper Agent Hardening Implementation Plan

> **For agentic workers:** Use TDD. Do not rewrite onto Agno/ADK/A2A. Extract small policy functions; do not grow `chat_orchestrator.py` further than necessary.

**Goal:** Stop same-turn paid generation, make chat jobs claimable/reapable, confirm costly music, cap spend mid-job, fix admin key leak, tighten RAG filters.

**Architecture:** Keep FastAPI + in-process `generation_jobs` + OpenRouter tool calling. Add policy gates in the existing orchestrator and CAS/reaper on the job table. No new runtime.

**Tech Stack:** FastAPI, SQLAlchemy async, pytest, Vite React.

## Global Constraints

- Work on branch `harden-agent-runtime` from `origin/main` only (do not include unrelated dirty files).
- English identifiers/comments; existing Polish UI copy is preserve.
- Do not read or commit `.env`.
- Do not enable video. Do not raise `music_variants_per_provider`.
- Do not add Agno/LangGraph/MCP.
- Tests first. `cd backend && poetry run pytest` and `poetry run ruff check .` must pass before commit.
- Commit frequently; do not push until the parent session says so (or push `harden-agent-runtime` only, not force-push main).

## Files

- Modify: `backend/teacher_helper/use_cases/chat_orchestrator.py`
- Modify: `backend/teacher_helper/infrastructure/jobs.py`
- Modify: `backend/teacher_helper/use_cases/chat_job_runner.py`
- Modify: `backend/teacher_helper/adapters/http/routes_chat.py`
- Modify: `backend/teacher_helper/adapters/http/deps.py` / `routes_admin.py` / `frontend/src/lib/api.ts`
- Modify: `backend/teacher_helper/use_cases/file_ops.py` (or `infrastructure/vector_search.py`)
- Create: `backend/tests/test_orchestrator_policy.py`
- Create: `backend/tests/test_generation_jobs.py`
- Modify: `docs/technical/decisions/chat-background-jobs.md` (delta)
- Modify: `AGENTS.md` learned facts if behavior changes

---

### Task 1: Clarification aborts paid tools

**Given** a completion that contains `ask_clarification` (or `request_video_confirmation`) **and** `generate_music` / `generate_graphics` / `generate_scenario` / `generate_video` / `generate_sfx` / `generate_study` / `generate_presentation` / `generate_poetry`  
**When** `_process_tool_calls` runs  
**Then** paid/module tools are skipped; user sees the clarification; `side_effects_skipped` is true.

Extract `def clarification_blocks_paid_tools(tool_names: set[str]) -> bool` next to `_tool_call_sort_key`.

- [ ] Write failing tests in `backend/tests/test_orchestrator_policy.py`
- [ ] Implement: if any blocking clarify tool is in the turn, skip `TOOL_TO_MODULE` / `edit_presentation` / `export_library_file` (keep search + reply + clarify)
- [ ] Also skip when `prepare_create_teacher_project` / `prepare_delete_teacher_project` is present alongside generate
- [ ] Run pytest on the new file
- [ ] Commit

### Task 2: Job CAS + one-active + reaper

**Given** a conversation already has `pending`/`running` chat job  
**When** `POST /v1/chat`  
**Then** 409 with the existing `job_id` (do not create a second job).

**Given** a job is `running` and `updated_at` older than 15 minutes  
**When** reaper runs (startup + before create)  
**Then** status becomes `error` with a Polish stale message.

- [ ] Tests for `claim_job_running` (only pending → running), `conversation_has_active_chat_job`, `reap_stale_running_jobs`
- [ ] `mark_job_running` must be CAS: `WHERE status='pending'`
- [ ] Hook reaper into app lifespan / chat POST
- [ ] Commit

### Task 3: Music confirm + default 1 variant

**Given** `generate_music` without a prior confirm in history  
**When** orchestrator runs  
**Then** do not call KIE/Lyria; ask for confirm with estimated USD; default variants = 1.

Reuse the existing video-confirm / folder-token pattern as far as possible. If a full token is too large, a same-turn block + prompt “napisz tak” (like video) is acceptable for v1, plus `music_variants_per_provider` default 1 in config.

- [ ] Tests for the block helper
- [ ] Implement
- [ ] Commit

### Task 4: Mid-job budget recheck

**Given** user is over monthly USD limit  
**When** a paid adapter is about to run inside the job  
**Then** skip remaining paid tools and append a Polish message.

`assert_user_within_monthly_cost_limit` already exists — call it before `_run_module` for paid modules (music, graphics, video, sfx).

- [ ] Test the guard helper
- [ ] Wire into `_process_tool_calls`
- [ ] Commit

### Task 5: Admin key not in SPA

**Given** admin UI  
**When** calling admin APIs  
**Then** only JWT admin role; no `VITE_ADMIN_API_KEY` header from the browser.

- [ ] Remove `getAdminKeyHeaders` usage from `frontend/src/lib/api.ts` and admin pages
- [ ] Backend: if `ADMIN_API_KEY` unset or request has no key, JWT admin is enough; do not require the Vite key
- [ ] Commit

### Task 6: RAG project filter + min score

**Given** semantic search with `project_id`  
**When** querying  
**Then** filter in SQL, not after over-fetch. Drop hits below min score.

- [ ] Tests if a pure function exists; otherwise unit-test the filter helper
- [ ] Commit

### Task 7: Docs + AGENTS.md delta

- [ ] ADR note on jobs: CAS + reaper
- [ ] AGENTS.md one-liner: clarification blocks paid tools; one active job

## Manual test checklist (after deploy)

Polish UI — short steps:

1. **Doprecyzowanie blokuje płatne narzędzia** — w Asystencie napisz ogólną prośbę („zrób przedstawienie o Aladynie”). Asystent ma zadać pytania; w „Moje materiały” **nie** pojawia się nowa piosenka / grafika w tej samej turze.
2. **Jedna aktywna job** — wyślij długą prośbę (np. prezentacja), od razu wyślij drugą w tej samej rozmowie. Druga ma wrócić z konfliktem (409) / komunikatem, że zadanie już trwa. Po zakończeniu pierwszej kolejna wiadomość przechodzi.
3. **Reaper** — nie testuj na produkcji bez potrzeby. Lokalnie: job `running` ze starym `updated_at` po restarcie API powinna przejść w `error` („utknęło”).
4. **Potwierdzenie muzyki** — „zrób piosenkę o wodzie”. Asystent podaje szacowany koszt i prosi o **tak**. Dopiero po „tak” pojawia się audio w bibliotece. Jeden wariant na dostawcę.
5. **Limit w trakcie joba** — konto blisko miesięcznego limitu USD: po wyczerpaniu asystent pomija dalszą muzykę/grafikę/SFX i pisze po polsku o limicie.
6. **Admin bez klucza w SPA** — zaloguj się jako admin (rola w JWT). Panel Użytkownicy i Monitoring ładują się **bez** `VITE_ADMIN_API_KEY`.
7. **RAG folder** — w katalogu z plikami zapytaj o treść z tego folderu (aktywny katalog / `project_id`). Trafienia spoza folderu i słabe podobieństwo nie powinny wracać.
