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
