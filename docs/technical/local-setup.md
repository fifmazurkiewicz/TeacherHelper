# Lokalne uruchomienie TeacherHelper

Delta względem [design spec](../superpowers/specs/2026-08-28-migracja-na-standard-vercel-render-supabase-design.md).  
Domyślna ścieżka dev: **bez Dockera** — natywny Postgres + backend Poetry + frontend Vite.

## Wymagania

- Python 3.11+
- [Poetry](https://python-poetry.org/)
- Node.js 20+ i npm
- PostgreSQL 15+ z rozszerzeniem **pgvector** (lokalnie) **lub** projekt Supabase Cloud (dev)
- Pliki env: skopiuj `backend/.env.example` → `.env` w **korzeniu repo**; `frontend/.env.example` → `frontend/.env`

Pełna lista nazw zmiennych: [configuration.md](./configuration.md).

## 1. Baza danych

**Opcja A — lokalny Postgres**

1. Utwórz bazę `teacher`.
2. Włącz rozszerzenie: `CREATE EXTENSION IF NOT EXISTS vector;`
3. Ustaw w `.env` (korzeń repo): `DATABASE_URL`, `DATABASE_URL_SYNC` → `localhost:5432`.

**Opcja B — Supabase Cloud (dev)**

1. Skopiuj connection string (Session mode / pooler dla produkcji; lokalnie możesz użyć direct lub dev pooler).
2. Ustaw `DATABASE_URL` / `DATABASE_URL_SYNC` oraz zmienne `SUPABASE_*` z dashboardu.

## 2. Migracje

```bash
cd backend
poetry install
poetry run alembic upgrade head
```

Na produkcji ustaw `SKIP_ADMIN_SEED=1` przed migracją (brak seeda admina).

## 3. Backend

```bash
cd backend
poetry run uvicorn teacher_helper.main:app --host 127.0.0.1 --port 8080
```

Lokalnie zalecane:

- `STORAGE_BACKEND=local` (pliki w `backend/data/storage`)
- `VIDEO_GENERATION_ENABLED=false` (domyślnie)

## 4. Frontend

```bash
cd frontend
npm ci
npm run dev
```

Dev proxy: żądania `/th-api/*` → `BACKEND_INTERNAL_URL` (domyślnie `http://127.0.0.1:8080`).

## 5. Smoke test

| Krok | Oczekiwany wynik |
|---|---|
| `GET http://127.0.0.1:8080/api/health` | `200`, `{ "status": "ok", ... }` |
| `GET http://127.0.0.1:8080/api/health/ready` | `200` gdy DB działa |
| Frontend `http://localhost:5173` | strona logowania ładuje się |
| Logowanie (Supabase Auth) | `GET /v1/auth/me` zwraca profil |

## 6. Definition of Done (lokalnie)

```bash
cd backend && poetry run ruff check .
cd backend && poetry run pytest
cd frontend && npm run lint && npm run build
```

## Uwagi

- **Graft CLI** na Windows może być niesprawny — patrz `AGENTS.md`.
- **Redis / Qdrant** nie są wymagane po migracji (pgvector + rate limit w Postgresie).
- Sekrety API (OpenRouter, Tavily, KIE, ElevenLabs) — ustaw lokalnie w `.env`; nie commituj.
