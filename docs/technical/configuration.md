# Konfiguracja — zmienne środowiskowe

Delta względem [design spec](../superpowers/specs/2026-08-28-migracja-na-standard-vercel-render-supabase-design.md).  
**Tylko nazwy** — wartości ustaw lokalnie w `.env` / Vercel / Render. Szablony: `backend/.env.example`, `frontend/.env.example`.

Plik `.env` backendu wczytywany jest z **korzenia repozytorium** (nie z `backend/`).

## ADDED (migracja na standard)

### Backend

| Zmienna | Opis |
|---|---|
| `SUPABASE_URL` | URL projektu Supabase |
| `SUPABASE_JWKS_URL` | JWKS do weryfikacji JWT (backend) |
| `SUPABASE_PROJECT_REF` | Ref projektu Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | Klucz service role (tylko backend, Storage) |
| `SUPABASE_STORAGE_BUCKET` | Nazwa bucketu Storage |
| `STORAGE_BACKEND` | `local` (dev) lub `supabase` (prod) |
| `VIDEO_GENERATION_ENABLED` | `true` / `false` — flaga Veo |
| `SKIP_ADMIN_SEED` | `1` na produkcji — pomija seed admina |
| `ADMIN_EMAILS` | Puste = bez auto-przypisania; np. `fifmazurkiewicz@gmail.com` — tylko te e-maile są adminem (Supabase Auth) |

### Frontend (prefiks `VITE_`)

| Zmienna | Opis |
|---|---|
| `VITE_SUPABASE_URL` | URL projektu Supabase |
| `VITE_SUPABASE_ANON_KEY` | Klucz anon (publiczny) |
| `VITE_API_URL` | Pełny URL API (prod); w dev opcjonalnie — domyślnie proxy `/th-api` |

## REMOVED

| Zmienna | Powód |
|---|---|
| `QDRANT_URL` | pgvector w Postgresie |
| `QDRANT_API_KEY` | j.w. |
| `QDRANT_COLLECTION` | j.w. |
| `REDIS_URL` | rate limit w Postgresie |
| `JWT_SECRET` | Supabase Auth |
| `JWT_ALGORITHM` | j.w. |
| `JWT_EXPIRE_HOURS` | j.w. |

## MODIFIED

| Zmienna | Lokalnie | Produkcja |
|---|---|---|
| `DATABASE_URL` | `localhost:5432` (async) | Supavisor pooler (async) |
| `DATABASE_URL_SYNC` | `localhost:5432` (sync, Alembic) | Supavisor pooler (sync) |
| `CORS_ORIGINS` | `http://localhost:5173`, `127.0.0.1:*` | Vercel + `teacherhelper.fmazurkiewicz.dev` |

## Bez zmian (wybrane, nadal używane)

Backend (korzeń `.env`): `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_MODULE_MODEL`, `OPENROUTER_IMAGE_MODEL`, `OPENAI_API_KEY`, `EMBEDDINGS_BACKEND`, `EMBEDDING_DIM`, `TAVILY_API_KEY`, `KIE_API_KEY`, `ELEVENLABS_API_KEY`, `XAI_API_KEY`, `ADMIN_API_KEY`, `CORS_ORIGINS`, `DEFAULT_RATE_LIMIT_RPM`, limity LLM (`LLM_DAILY_*`, `DEFAULT_USER_LLM_DAILY_TOKEN_LIMIT`), chat context (`CHAT_*`), opcjonalnie Langfuse / alerty.

Frontend (`frontend/.env`): `BACKEND_INTERNAL_URL`, opcjonalnie `VITE_ADMIN_API_KEY`.

## Platformy

| Platforma | Gdzie ustawić |
|---|---|
| Render (backend) | Dashboard → Environment — wszystkie backendowe + `DATABASE_URL` przez pooler |
| Vercel (frontend) | `VITE_*` + ewentualnie build env |
| Supabase | Auth providers (Google OAuth), Storage bucket, DB connection strings |

Szczegóły wdrożenia: `.cursor/plans/2026-08-28-standard-deploy.md`.

## Langfuse (opcjonalnie)

| Zmienna | Opis |
|---|---|
| `LANGFUSE_PUBLIC_KEY` | Klucz publiczny projektu Langfuse |
| `LANGFUSE_SECRET_KEY` | Klucz secret (tylko backend) |
| `LANGFUSE_HOST` | Domyślnie `https://cloud.langfuse.com` |

Gdy klucze są ustawione, wywołania LLM z czatu trafiają do Langfuse z `session_id = conversation_id` (jedna sesja = jedna rozmowa). Szczegóły: `docs/superpowers/specs/2026-08-31-langfuse-conversation-sessions-design.md`.
