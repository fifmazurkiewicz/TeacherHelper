# TeacherHelper — agent guide

## Stack

| Layer | Platform |
|---|---|
| Frontend | **Vercel** (Vite SPA) |
| Backend | **Render** (Docker Web Service) |
| Database | **Supabase Postgres** + **pgvector** |
| Auth | **Supabase Auth** (e-mail + Google OAuth) |
| Storage | **Supabase Storage** (signed URLs) |

## Domains

| Service | URL |
|---|---|
| Frontend | `teacherhelper.fmazurkiewicz.dev` |
| Backend API | `api-teacherhelper.fmazurkiewicz.dev` |

## Commands

### Backend

```bash
cd backend && poetry run ruff check .
cd backend && poetry run pytest
cd backend && poetry run uvicorn teacher_helper.main:app --host 127.0.0.1 --port 8080
```

### Frontend

```bash
cd frontend && npm run lint && npm run build
```

## Graft

Graft CLI is broken on Windows (missing native build / `@nanonets/graft/dist/cli.js`). Manual wiring (`.cursor/rules/graft.mdc`, `.cursorignore`, `/graft/` in gitignore) is OK. Retry `npx @nanonets/graft init` after VS C++ build tools are installed.

## Docs

- Design spec: `docs/superpowers/specs/2026-08-28-migracja-na-standard-vercel-render-supabase-design.md`
- User approval gate: `docs/superpowers/specs/2026-09-07-user-approval-gate-design.md`
- Working plan: `.cursor/plans/2026-08-28-standard-deploy.md`
- Local setup: `docs/technical/local-setup.md`
- Configuration (variable names): `docs/technical/configuration.md`
- ADRs: `docs/technical/decisions/`

## Learned User Preferences

- Krótkie dźwięki/SFX (do ~30 s) to nie muzyka — osobna ścieżka (ElevenLabs), nie KIE/Lyria.
- Instrukcje wdrożeniowe preferowane krok po kroku z konkretnymi polami w panelach (Supabase, Google Cloud, Render, Vercel); migracje bez auto-Alembic — gotowy SQL do wklejenia w SQL Editor.
- Nie przepisywać orchestratora na Agno/ADK/A2A — zostaje custom FastAPI + OpenRouter; tylko real value, nie AI-hype.
- Gdy główny checkout ma WIP: implementacja na izolowanym worktree (`_harden/<repo>`), bez ruszania brudnego katalogu.
- Przed merge: code review/audit; po deploy: krótka angielska checklista + logi Render/Vercel (deploy z `main` jest automatyczny).
- Personal control room (nie feature TeacherHelper): GitHub Projects v2 + Issues + label `ready` → Cloud Agent; Slack `@Cursor`; spec `docs/superpowers/specs/2026-09-06-personal-agent-control-room-design.md`.
- Aplikacje z FM Landing (TeacherHelper, Langy, Coach/goat, Medical Intelligence, Family Organiser) — wspólna bramka `is_approved` (login OK, jedna waiting screen, Accept/Revoke). Family Organiser też Vercel + Render, bez limitu LLM $10.

## Learned Workspace Facts

- Frontend dev (Vite): `http://127.0.0.1:18080` (`npm run dev`); backend lokalnie `:8080`.
- RAG (pgvector): wyszukiwanie fragmentów biblioteki w czacie oraz semantyczne omówienie tematu (Topic Studio); zastąpił Qdrant.
- Agent runtime: custom FastAPI + OpenRouter tool-calling + in-process `generation_jobs` (Render Free, jeden proces). Bez Agno/ADK/A2A/LangGraph.
- Audio/wideo: SFX ≤30 s → ElevenLabs; utwory → KIE; Lyria (OpenRouter) ~$0.16/wywołanie; wideo domyślnie wyłączone (`VIDEO_GENERATION_ENABLED=false`).
- Mobile czat (`/assistant`): `useChatShell` + `--vvh` z `visualViewport`; safe-area; admin ⋮. Odświeżenie wznawia polling joba: `activeJob` w `sessionStorage` + fallback `GET /v1/conversations/{id}/active-job`.
- Obserwowalność: Langfuse — wywołania LLM/API; rozliczenia i limity — `llm_usage_log`. Bez Langfuse: polling KIE, pobrania, storage, Tavily, Veo.
- Google OAuth (dev): Authorized JavaScript origins — `http://localhost:18080` i `http://127.0.0.1:18080`; redirect URI to callback Supabase, nie frontend.
- Render + Supabase: pooler (`*.pooler.supabase.com`), nie direct `db.*.supabase.co` (IPv6); `DATABASE_URL` → port 6543 (`+asyncpg`); `DATABASE_URL_SYNC` → 5432 (`+psycopg`); migracje Alembic auto przy starcie kontenera (`entrypoint.sh`).
- Rejestracja bez whitelisty maili (Supabase Auth); nowi userzy logują się, ale funkcje czekają na Accept admina (`is_approved`, waiting screen, 403 `account_pending_approval`); `ADMIN_EMAILS` auto-approved tylko przy insercie; seed admina wyłączany przez `SKIP_ADMIN_SEED=1`.
- Panel admina (`/admin/users`): Accept/Revoke w kolumnie Akcje (badge Oczekuje nie jest klikalny); rola admin w JWT; `ADMIN_API_KEY` tylko dla skryptów (nie w SPA).
- Czat: `ask_clarification` / potwierdzenie wideo / prepare projektu w tej samej turze blokuje płatne `generate_*`; jedna aktywna job na rozmowę (409 + reaper 15 min).
- Domyślne: limit LLM **$10/miesiąc UTC** (`DEFAULT_USER_LLM_MONTHLY_COST_LIMIT_USD`; Accept nie nadpisuje NULL); modele OpenRouter `google/gemini-3.1-flash-lite-preview` (orchestrator), `google/gemini-3-flash-preview` (moduły).
