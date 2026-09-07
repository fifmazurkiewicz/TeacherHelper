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
- Instrukcje wdrożeniowe preferowane krok po kroku z konkretnymi polami w panelach (Supabase, Google Cloud, Render, Vercel).

## Learned Workspace Facts

- Frontend dev (Vite): `http://127.0.0.1:18080` (`npm run dev`); backend lokalnie `:8080`.
- RAG (pgvector): wyszukiwanie fragmentów biblioteki w czacie oraz semantyczne omówienie tematu (Topic Studio); zastąpił Qdrant.
- Produkcja: baza Supabase od zera (bez migracji danych z GCP); seed admina wyłączany przez `SKIP_ADMIN_SEED=1`.
- Generowanie wideo domyślnie wyłączone (`VIDEO_GENERATION_ENABLED=false`); kod Veo zostaje w repo.
- Audio: SFX ≤30 s → ElevenLabs; utwory/piosenki → KIE (Lyria przez OpenRouter ~$0.16/wywołanie — droższa od KIE).
- Mobile czat (`/assistant`): `useChatShell` + `--vvh` z `visualViewport` (nie `100vh`); safe-area na composerze; admin na telefonie w menu ⋮.
- Google OAuth (dev): Authorized JavaScript origins — `http://localhost:18080` i `http://127.0.0.1:18080`; redirect URI to callback Supabase, nie frontend.
- Render + Supabase: pooler (`*.pooler.supabase.com`), nie direct `db.*.supabase.co` (IPv6); `DATABASE_URL` → port 6543 (`+asyncpg`); `DATABASE_URL_SYNC` → 5432 (`+psycopg`); migracje Alembic auto przy starcie kontenera (`entrypoint.sh`).
- Rejestracja bez whitelisty maili (Supabase Auth); nowi userzy logują się, ale funkcje czekają na Accept admina (`is_approved`, waiting screen, 403 `account_pending_approval`); `ADMIN_EMAILS` auto-approved tylko przy insercie.
- Panel admina: rola admin w JWT; `ADMIN_API_KEY` tylko dla skryptów (nie w SPA).
- Czat: `ask_clarification` / potwierdzenie wideo / prepare projektu w tej samej turze blokuje płatne `generate_*`; jedna aktywna job na rozmowę (409 + reaper 15 min).
- Domyślny limit LLM: **$10/miesiąc UTC** na zaakceptowanego użytkownika (`DEFAULT_USER_LLM_MONTHLY_COST_LIMIT_USD`); Accept nie nadpisuje `llm_monthly_cost_limit_usd`.
- Domyślne modele OpenRouter: `google/gemini-3.1-flash-lite-preview` (orchestrator), `google/gemini-3-flash-preview` (moduły).
