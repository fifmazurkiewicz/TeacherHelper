# Migracja TeacherHelper na standard: Vercel + Render + Supabase

**Data:** 2026-08-28
**Status:** zaakceptowany design, przed planem implementacyjnym
**Zakres:** brownfield, delta względem `main` (381c517)

## 1. Cel

Doprowadzić TeacherHelper do stanu, w którym działa publicznie pod `teacherhelper.fmazurkiewicz.dev`
na standardowym stacku (`deployment-standard.mdc`), z pełną zgodnością zamiast odstępstw,
oraz uzupełnić brakującą higienę repozytorium (wiring reguł, AGENTS.md, CI, pierwsze testy).

Bazy danych stawiamy **od zera** — nie migrujemy danych ani kont użytkowników.

## 2. Stan wyjściowy (audyt 2026-08-28)

| Obszar | Stan obecny |
|---|---|
| Backend | FastAPI, clean architecture, SQLAlchemy async + Alembic, Postgres |
| Wektory | Qdrant (`qdrant-client`), embeddingi dublowane w `file_chunks.embedding` (JSONB) |
| Pliki | `LocalStorage` → dysk `data/storage` (6 miejsc użycia) |
| Rate limit | Redis (`redis://`), z cichym fallbackiem gdy niedostępny |
| Auth | własne JWT: bcrypt + python-jose, `POST /v1/auth/register`, `/login` |
| Health | `GET /health` |
| Frontend | React 18 + Vite SPA, Tailwind, 7 stron; `api.ts` czyta `VITE_API_URL` z fallbackiem `/th-api` |
| Deploy | GCP: Compute Engine + docker-compose + Cloud SQL + Qdrant Cloud + Caddy |
| Testy | brak (`testpaths = ["tests"]` bez katalogu); `npm run lint` woła nieistniejącego eslinta |
| Wiring | brak `AGENTS.md`, `.cursor/rules/`, `.cursor/plans/`, `.cursorignore`, `.github/`, `docs/technical/` |
| Graft | CLI zepsute (brak `@nanonets/graft/dist/cli.js`), brak `.cursor/mcp.json` |

Branche: `main` czysty; zmergowane `feature/pptx`, `feature/veo`, `claude/add-sound-generation-DB8AY`,
`claude/practical-tu` (+ prunable worktree); niezmergowany `claude/cloud-deployment-guide-ok95y` (instrukcja GCP — nieaktualna).

## 3. Decyzje (2026-08-28)

| # | Decyzja | Uzasadnienie |
|---|---|---|
| D1 | Pełna zgodność ze standardem, bazy od zera | brak migracji danych upraszcza auth i schemat |
| D2 | pgvector zamiast Qdrant Cloud | embeddingi już są w Postgresie; jeden dostawca mniej, jeden klucz mniej |
| D3 | Supabase Storage zamiast dysku, **bez limitów i retencji** | Render Free nie ma trwałego dysku; zużycie pilnujemy w dashboardzie |
| D4 | Rate limit w Postgresie zamiast Redisa | Redis nie mieści się w darmowym starcie |
| D5 | Zadania w tle w procesie web service'u, bez płatnego workera | Background Worker na Render kosztuje od $7/mc |
| D6 | `POST /v1/chat` zwraca `202` + `job_id`, front odpytuje status | ciężkie narzędzia wykonują się wewnątrz tury czatu |
| D7 | Supabase Auth: e-mail + hasło oraz Google OAuth | zachowuje obecny UX, dokłada wejście jednym kliknięciem |
| D8 | Generowanie wideo (Veo) wyłączone flagą, **kod zostaje nietknięty** | koszt i waga plików; użytkownik dostaje jasny komunikat |
| D9 | Pozostałe płatne integracje aktywne (grafika, muzyka KIE + Lyria, SFX, Tavily) | pełne demo produktu |
| D10 | Tylko produkcja, bez środowiska staging | jeden projekt Supabase, jedna usługa Render |
| D11 | Zakres „polish”: higiena repo + jakość, bez przebudowy UI | odświeżenie UI jako osobny temat |

Odstępstw od `deployment-standard.mdc` **brak**.

## 4. Architektura docelowa

```
Przeglądarka
  ├─ teacherhelper.fmazurkiewicz.dev      → Vercel (statyczny build Vite)
  ├─ api-teacherhelper.fmazurkiewicz.dev  → Render (Docker Web Service, Free)
  └─ Supabase Auth (logowanie, tokeny)

Render backend
  ├─ Supabase Postgres (dane + pgvector) przez pooler Supavisor
  ├─ Supabase Storage (pliki, signed URL)
  └─ API zewnętrzne: OpenRouter, OpenAI, KIE, ElevenLabs, Tavily
```

Frontend woła API **bezpośrednio** (`VITE_API_URL`), bez rewrite'ów przez Vercela — długie odpowiedzi
nie wpadają w limit funkcji Hobby, a transfer nie przechodzi przez Vercela.
Proxy `/th-api` w `vite.config.ts` zostaje wyłącznie jako ścieżka dev.

Znikają: Qdrant Cloud, Redis, `deploy/gcp/`, `nginx/`, rootowy `docker-compose.yml`.

## 5. Komponenty i granice

### 5.1 Wyszukiwanie wektorowe (MODIFIED)

`file_chunks.embedding`: JSONB → `vector(1536)` + indeks HNSW.
`infrastructure/qdrant.py` znika, zastępuje go zapytanie SQL w warstwie infrastruktury.
**Sygnatura `semantic_search_chunks(session, user_id, query, top_k, project_id, topic_id)` nie zmienia się**,
więc `chat_orchestrator` (narzędzie `search_library_fragments`) i `routes_topics`
(wyszukiwanie w Omówieniu tematu) pozostają bez zmian.
Izolacja po `user_id` i `topic_id` idzie do `WHERE`, zamiast filtra payloadu Qdranta.

### 5.2 Storage (ADDED adapter)

Nowy `SupabaseStorage` o interfejsie identycznym z `LocalStorage`; wybór przez `STORAGE_BACKEND`
(`local` lokalnie, `supabase` na produkcji). Pobieranie plików przez **signed URL**, nie przez
strumień z backendu. Zapis strumieniowy — bez trzymania całego pliku w pamięci.

### 5.3 Zadania w tle (ADDED)

Tabela `generation_jobs`: `id`, `user_id`, `kind`, `status` (`pending|running|done|error`),
`payload`, `result`, `error`, `created_at`, `updated_at`.
`POST /v1/chat` → `202 {job_id}`; wykonanie jako zadanie w tle w tym samym procesie;
`GET /v1/jobs/{id}` zwraca status i wynik. Odpytywanie z frontu utrzymuje instancję Render wybudzoną.

### 5.4 Rate limit (MODIFIED)

Licznik okna czasowego w Postgresie zamiast Redisa; `redis_url` i zależność `redis` wypadają.

### 5.5 Health (MODIFIED)

`GET /api/health` — liveness bez dotykania bazy (Render wymaga odpowiedzi w 5 s).
`GET /api/health/ready` — ping bazy, `503` przy awarii.
`GET /health` zostaje jako alias.

### 5.6 Auth (MODIFIED)

Frontend: `@supabase/supabase-js`, `signUp` / `signInWithPassword` / `signInWithOAuth('google')`;
token z sesji Supabase zamiast własnego `th_access_token` w `localStorage`.
Backend: weryfikacja JWT przez JWKS Supabase (PyJWT z cache kluczy), bez `supabase-py`.
`users` zostaje profilem aplikacyjnym: `id` = identyfikator z Supabase Auth, rola i dzienny limit tokenów
po naszej stronie; profil zakładany przy pierwszym uwierzytelnionym żądaniu.
Endpointy `register`/`login` znikają, `GET /v1/auth/me` zostaje.
Seed admina (`migracja 007`) wyłączony na produkcji przez `SKIP_ADMIN_SEED=1`; historia migracji append-only.

### 5.7 Flaga wideo (ADDED)

`VIDEO_GENERATION_ENABLED` (domyślnie `false`): narzędzie `generate_video` nie trafia do listy narzędzi
orchestratora, a próba użycia kończy się komunikatem, że funkcja jest chwilowo niedostępna.
Kod adaptera Veo pozostaje nietknięty — bez usuwania i bez komentowania.

### 5.8 Puls API (ADDED, frontend)

`ApiPulseProvider` w korzeniu, hook `useApiPulse`, `ApiPulseBanner`.
Odpytywanie: 5 s gdy niezdrowe, 30 s gdy zdrowe, timeout 8 s na próbę.
Po powrocie do zdrowia — ponowienie odłożonych żądań.

### 5.9 Zmienne środowiskowe (delta, same nazwy)

ADDED: `SUPABASE_URL`, `SUPABASE_JWKS_URL`, `SUPABASE_PROJECT_REF`, `SUPABASE_SERVICE_ROLE_KEY`
(tylko backend), `SUPABASE_STORAGE_BUCKET`, `STORAGE_BACKEND`, `VIDEO_GENERATION_ENABLED`,
`SKIP_ADMIN_SEED`; frontend: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_URL`.

REMOVED: `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`, `REDIS_URL`, `JWT_SECRET`,
`JWT_ALGORITHM`, `JWT_EXPIRE_HOURS`.

MODIFIED: `DATABASE_URL` / `DATABASE_URL_SYNC` — na produkcji przez pooler Supavisor,
lokalnie `localhost:5432`; `CORS_ORIGINS` — domena Vercel i podglądy.

Każda zmiana trafia równolegle do `.env.example`, `frontend/.env.example`
i `docs/technical/local-setup.md`. Wartości sekretów nie pojawiają się w repozytorium.

## 6. Wymagania (Given / When / Then)

**W1 — wyszukiwanie na pgvector**
Given użytkownik ma zaindeksowany plik z frazą „fotosynteza”,
When orchestrator wywoła `search_library_fragments` z zapytaniem o fotosyntezę,
Then dostanie fragmenty tylko z plików tego użytkownika, posortowane po podobieństwie.

**W2 — izolacja tematów**
Given dwa tematy tego samego użytkownika z różnymi źródłami,
When wyszukujemy w temacie A,
Then w wynikach nie ma ani jednego chunku z tematu B.

**W3 — pliki na Supabase Storage**
Given `STORAGE_BACKEND=supabase`,
When użytkownik wgra plik i po restarcie instancji poprosi o pobranie,
Then dostaje plik przez signed URL, bez błędu „nie znaleziono”.

**W4 — zadanie w tle**
Given użytkownik wysłał wiadomość uruchamiającą generowanie grafiki,
When zamknie kartę przeglądarki i wróci po minucie,
Then zadanie ma status `done`, a odpowiedź i pliki są w rozmowie.

**W5 — health dla Rendera**
Given baza jest niedostępna,
When Render odpyta `GET /api/health`,
Then dostaje `200` w mniej niż 5 s, a `GET /api/health/ready` zwraca `503`.

**W6 — auth Supabase**
Given żądanie z tokenem podpisanym kluczem spoza JWKS projektu,
When trafi na chroniony endpoint,
Then backend odpowiada `401` i nie zakłada profilu użytkownika.

**W7 — pierwszy login zakłada profil**
Given nowy użytkownik zalogowany przez Google,
When wykona pierwsze żądanie do `GET /v1/auth/me`,
Then w bazie istnieje profil z rolą `teacher` i domyślnym limitem tokenów.

**W8 — wideo wyłączone**
Given `VIDEO_GENERATION_ENABLED=false`,
When użytkownik poprosi w czacie o wygenerowanie filmu,
Then dostaje komunikat o chwilowej niedostępności funkcji, bez błędu i bez wywołania API Veo.

**W9 — rate limit bez Redisa**
Given brak jakiejkolwiek instancji Redis,
When użytkownik przekroczy limit żądań na minutę,
Then dostaje `429`, a licznik pochodzi z Postgresa.

**W10 — puls API po cold starcie**
Given backend na Render śpi po 15 minutach ciszy,
When użytkownik otworzy aplikację,
Then widzi baner budzenia API, a po odpowiedzi `/api/health` interfejs sam wraca do działania.

**W11 — Definition of Done**
Given świeży klon repozytorium,
When wykonam komendy z `AGENTS.md` (lint, testy, build),
Then wszystkie kończą się sukcesem, a CI na GitHubie jest zielone.

## 7. Poza zakresem

- Przebudowa UI i design system (osobny temat, z udziałem `ux-ui-challenger`).
- Środowisko staging i preview z osobną bazą.
- Włączenie generowania wideo.
- Limity miejsca na użytkownika i retencja plików.
- Folder `research/` — zostaje nietknięty, wypada tylko z CI.

## 8. Ryzyka

| Ryzyko | Reakcja |
|---|---|
| 512 MB RAM przy PPTX z osadzonymi grafikami | strumieniowanie do Storage, brak buforowania całości |
| 500 MB bazy na Supabase Free (chunki + embeddingi) | monitoring rozmiaru, chunk 480 znaków bez zmian |
| Cold start 30–60 s po 15 min ciszy | puls API + baner, odpytywanie zadań trzyma instancję |
| Google OAuth wymaga konfiguracji poza repo | krok wykonuje użytkownik w Google Cloud i Supabase |
| Graft CLI niesprawny na Windows | wiring ręczny + notatka w `AGENTS.md`, ponowna próba instalacji |

## 9. Kolejność realizacji

1. Higiena repo i wiring (reguły, `AGENTS.md`, `.cursorignore`, plan, ADR).
2. Health, flaga wideo, rate limit bez Redisa.
3. pgvector zamiast Qdranta.
4. Adapter Supabase Storage.
5. Auth: backend JWKS + frontend Supabase.
6. Zadania w tle i odpytywanie z frontu.
7. Puls API, `vercel.json`, naprawa lintu frontendu.
8. CI (ruff, pytest, tsc, eslint), Dependabot, secret scanning.
9. Wdrożenie: projekt Supabase → Render → Vercel → DNS w Cloudflare → smoke test.
10. Dokumentacja: README, `docs/technical/local-setup.md`, `configuration.md`, ADR-y, archiwizacja instrukcji GCP.
