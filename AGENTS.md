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
- Audio: SFX ≤30 s → ElevenLabs; utwory/piosenki → KIE (+ opcjonalnie Lyria przez OpenRouter).
- Szablon zmiennych: kanoniczny plik to `.env.example` w katalogu głównym repozytorium.
- Google OAuth (dev): Authorized JavaScript origins — `http://localhost:18080` i `http://127.0.0.1:18080`; redirect URI to callback Supabase, nie frontend.
