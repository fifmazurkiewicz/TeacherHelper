# TeacherHelper

Asystent AI dla nauczycieli — generowanie materiałów edukacyjnych (scenariusze, grafiki, piosenki, wiersze, prezentacje), baza plików z wyszukiwaniem semantycznym, czat z orchestracją modułów (tool calling).

**Założenia produktowe i flow (w tym „Omówienie tematu” w stylu NotebookLM):** zobacz [docs/ZASADY_I_WYMAGANIA.md](docs/ZASADY_I_WYMAGANIA.md) oraz [docs/komponenty/core-topic-studio.md](docs/komponenty/core-topic-studio.md).

## Architektura

```
backend/   → FastAPI, Clean Architecture, PostgreSQL, Qdrant, Redis
frontend/  → React 18 + Vite, Tailwind CSS
```

**Modele LLM** (przez OpenRouter, jeden klucz API):
- Orchestrator (czat): `gemini-3.1-flash-lite` — tani, szybki
- Moduły (generowanie treści): `gemini-3-flash` — reasoning
- Grafika: `gemini-3.1-flash-image` — generowanie obrazów

## Wdrożenie (Google Cloud)

Instrukcja krok po kroku: [docs/GCP_KROK_PO_KROKU.md](docs/GCP_KROK_PO_KROKU.md) — Cloud SQL, Compute Engine, Docker Compose w `deploy/gcp/` (Ścieżka A: zarządzany Postgres; w dodatku opcjonalnie Ścieżka B z Postgresem w kontenerze).

## Uruchomienie lokalne — krok po kroku

### Wymagania

- **Python 3.11+** + **Poetry**
- **Node.js 18+** i npm
- **Ubuntu/WSL** (PostgreSQL, Qdrant, Redis)
- **DBeaver** (opcjonalnie, do zarządzania bazą)
- Klucz **OpenRouter API** → https://openrouter.ai/keys
- Klucz **OpenAI API** (embeddingi) → https://platform.openai.com/api-keys

---

### Krok 1: PostgreSQL (Ubuntu/WSL)

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib -y
sudo service postgresql start
```

Utwórz bazę i użytkownika:

```bash
sudo -u postgres psql
```

W konsoli `psql`:

```sql
CREATE USER teacher WITH PASSWORD 'teacher';
CREATE DATABASE teacherhelper OWNER teacher;
\q
```

Baza działa na `localhost:5432`. W DBeaver połączysz się: host `localhost`, port `5432`, database `teacherhelper`, user `teacher`, password `teacher`.

---

### Krok 2: Qdrant (Ubuntu/WSL)

```bash
docker run -d --name qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v qdrant_data:/qdrant/storage \
  qdrant/qdrant:v1.12.6
```

Dashboard: http://localhost:6333

---

### Krok 3: Redis (Ubuntu/WSL)

```bash
sudo apt install redis-server -y
sudo service redis-server start
```

Sprawdzenie: `redis-cli ping` → `PONG`

---

### Krok 4: Backend — instalacja zależności

W PowerShell, w katalogu projektu:

```powershell
cd backend
poetry install
```

---

### Krok 5: Backend — konfiguracja (.env)

```powershell
cp .env.example .env
```

Otwórz `backend/.env` i uzupełnij **wymagane** klucze:

```
OPENROUTER_API_KEY=sk-or-...twój-klucz...
OPENAI_API_KEY=sk-...twój-klucz...
JWT_SECRET=wygeneruj-losowy-ciag-min-32-znaki
```

Reszta ma sensowne domyślne wartości.

---

### Krok 6: Backend — migracje bazy danych

```powershell
cd backend
poetry run alembic upgrade head
```

Bez Poetry (venv + `pip install -r requirements.txt`): `python -m alembic upgrade head` — katalog migracji nazywa się `migrations/`, żeby nie kolidował z paczką `alembic`.

To stworzy wszystkie tabele (users, projects, file_assets, file_chunks, conversations, messages, llm_usage_log, system_incidents).

---

### Krok 7: Backend — uruchomienie

```powershell
cd backend
poetry run uvicorn teacher_helper.main:app --reload --host 0.0.0.0 --port 8080
```

API działa pod `http://localhost:8080`. Dokumentacja Swagger: `http://localhost:8080/docs` (domyślnie włączona; wyłączenie: `OPENAPI_DOCS=false` w `.env`).

---

### Krok 8: Frontend — przygotowanie

W nowym terminalu PowerShell:

```powershell
cd frontend
cp .env.example .env.local
npm install
```

Skopiuj `frontend/.env.example` → `.env.local`. **Domyślnie** front woła API przez **`/th-api`** (Vite proxy na `BACKEND_INTERNAL_URL`, zwykle `http://127.0.0.1:8080`) — nie ustawiaj `VITE_API_URL`, chyba że celowo omijasz proxy.

---

### Krok 9: Frontend — uruchomienie

```powershell
cd frontend
npm run dev
```

Aplikacja domyślnie: `http://127.0.0.1:18080` (`npm run dev`) — na części instalacji Windows **3000** zwraca `EACCES` (Hyper-V / wykluczone porty). Gdy u Ciebie **3000 działa**, możesz użyć `npm run dev:3000`.

---

### Krok 10: Pierwsze użycie

1. Otwórz `http://127.0.0.1:18080` w przeglądarce (albo `:3000` jeśli używasz `npm run dev:3000`)
2. Zarejestruj się (pierwszy użytkownik dostaje rolę `teacher`)
3. Aby nadać konto admin — w DBeaver:
   ```sql
   UPDATE users SET role = 'admin' WHERE email = 'twoj@email.pl';
   ```
4. Przejdź do sekcji **Asystent** i napisz np. „Przygotuj scenariusz jasełek dla klasy 3"

---

## Szybka kontrola statusu

| Usługa     | URL                          | Sprawdzenie              |
|------------|------------------------------|--------------------------|
| Backend    | http://localhost:8080/health | `{"status": "ok"}`       |
| PostgreSQL | localhost:5432               | DBeaver                  |
| Qdrant     | http://localhost:6333        | Dashboard w przeglądarce |
| Redis      | localhost:6379               | `redis-cli ping`         |
| Frontend   | http://127.0.0.1:18080       | `npm run dev` (alternatywa: `dev:3000` → :3000) |

## Struktura projektu

```
TeacherHelper/
├── backend/
│   ├── .env.example              ← skopiuj jako .env
│   ├── pyproject.toml            ← zależności (Poetry)
│   ├── alembic.ini
│   ├── migrations/versions/      ← migracje Alembic (nazwa inna niż „alembic”, żeby `python -m alembic` działało)
│   └── teacher_helper/
│       ├── main.py               ← punkt wejścia ASGI
│       ├── config.py             ← ustawienia z .env
│       ├── domain/entities.py    ← encje domenowe
│       ├── use_cases/
│       │   ├── ports.py          ← interfejsy (protokoły)
│       │   └── chat_orchestrator.py ← logika czatu + tool calling
│       ├── adapters/http/        ← FastAPI routes
│       └── infrastructure/
│           ├── factories.py      ← fabryki LLM + mediów
│           ├── llm_openrouter.py ← klient OpenRouter
│           ├── image_openrouter.py ← generator obrazów
│           ├── image_dalle.py    ← generator DALL-E (fallback)
│           ├── embeddings.py     ← embeddingi OpenAI
│           ├── qdrant.py         ← wyszukiwanie wektorowe
│           └── db/               ← modele SQLAlchemy, operacje
├── frontend/
│   ├── .env.example              ← skopiuj jako .env.local
│   ├── package.json
│   └── src/                      ← React (Vite SPA)
├── deploy/gcp/                   ← docker-compose (GCP) + przykładowe .env
├── docs/                         ← ZASADY, komponenty, GCP, analiza cen muzyki, benchmarki
├── research/
│   ├── music-provider-benchmark/ ← osobna mini-aplikacja FastAPI (porównanie API muzyki)
│   └── image-provider-benchmark/ ← to samo dla grafiki (OpenAI, Stability, OpenRouter image)
└── docker-compose.yml            ← opcjonalnie (PG przez Docker)
```

## Badania: benchmark dostawców muzyki (`research/music-provider-benchmark`)

Osobny projekt **niepodłączany** do `uvicorn teacher_helper` — służy do **ręcznego / półautomatycznego** porównania tych samych danych wejściowych (tytuł, styl, tekst, długość) na **wielu dostawcach naraz** (m.in. **KIE Suno**, **WaveSpeed MiniMax**, **OpenRouter Lyria**, **Seedance**, opcjonalnie **ElevenLabs Music**).

- **Uruchomienie:** szczegóły, zmienne `.env` i flow `model-catalog` → `preview` → `run` — w [research/music-provider-benchmark/README.md](research/music-provider-benchmark/README.md).
- **Wyniki i wnioski (jakość, koszty, ograniczenia API):** [docs/wnioski-z-benchmarku-muzyki-prowiderzy.md](docs/wnioski-z-benchmarku-muzyki-prowiderzy.md).
- **Publiczne ceny i modele (MiniMax, KIE, ElevenLabs, OpenRouter / Lyria):** [docs/analiza-cen-modeli-muzyki.md](docs/analiza-cen-modeli-muzyki.md) — m.in. ujęcie **Lyria vs KIE** (jawna stawka Lyrii vs kredyty Suno bez tabeli per model w OpenAPI) oraz **V4_5ALL vs inne modele KIE** w warstwie dokumentacji.

**Podsumowanie benchmarku (co robi narzędzie):**

- Jedno **wejście tekstowe** (tytuł, styl, słowa, długość docelowa) → **równoległe** wywołania wybranych dostawców; odpowiedź JSON z **`trace`** (kroki HTTP) i **`artifacts`** (MP3/WAV/wideo: base64 lub link CDN).
- **KIE** i **WaveSpeed** trafiają do podglądu **tylko**, gdy dodasz odpowiedni wiersz w UI; **Lyria / Seedance / ElevenLabs** — według wierszy w `model_rows`.
- **Lyria** na OpenRouter: żądanie z **`modalities` + `audio`** oraz **`stream: true`** (wymóg platformy przy wyjściu audio); szczegóły w kodzie `research/music-provider-benchmark/benchmark/openrouter_media.py`.
- W katalogu modeli OpenRouter (muzyka) **pomijane są identyfikatory zawierające `clip`** — porównanie skupia się na **Lyria Pro** i pokrewnych; pełna lista nadal dostępna bezpośrednio z API OpenRouter.

Folder `research/` można usunąć bez wpływu na produkcyjny backend TeacherHelper.

## Badania: benchmark dostawców grafiki (`research/image-provider-benchmark`)

Ten sam wzorzec co muzyka: **`GET /api/model-catalog`** → **`POST /api/preview`** → edycja JSON → **`POST /api/run`**. Dostawcy w MVP: **OpenAI** (Images / DALL·E), **Stability** (Stable Image v2beta), **OpenRouter** (modele z `output_modalities=image`). Szczegóły: [research/image-provider-benchmark/README.md](research/image-provider-benchmark/README.md).

## Testy automatyczne (stan repozytorium)

W **backend** i **frontend** nie ma na razie wydzielonej, opisanej w README suite’u testów jednostkowych (np. `pytest` / `vitest`) jako standardowego kroku CI — regresje sprawdza się głównie **ręcznie** oraz przez **zewnętrzne API** w ramach benchmarku muzyki powyżej.

**Checklista ręczna aplikacji (orientacyjnie przed releasem / po większej zmianie):**

| Obszar | Działanie |
|--------|-----------|
| Backend | `GET /health` → `{"status":"ok"}` |
| Auth | rejestracja, logowanie, `GET /v1/auth/me` |
| Frontend | logowanie, **Asystent** — przykładowa wiadomość z odpowiedzią |
| Integracje | wg potrzeb: upload pliku, czat z narzędziami — zgodnie z [ZASADY_I_WYMAGANIA](docs/ZASADY_I_WYMAGANIA.md) |

## Endpointy API

- `GET /health` — status
- `POST /v1/auth/register` — rejestracja
- `POST /v1/auth/login` — logowanie (zwraca JWT)
- `GET /v1/auth/me` — dane zalogowanego użytkownika
- `GET/POST /v1/projects` — projekty
- `GET/POST /v1/conversations` — rozmowy (historia czatu)
- `GET /v1/conversations/{id}/messages` — wiadomości w rozmowie
- `GET/POST /v1/files` — pliki
- `POST /v1/chat` — czat z orchestracją modułów (pole `conversation_id` opcjonalne przy pierwszej wiadomości)
- `POST /v1/intent/analyze` — analiza intencji (diagnostyka)
- `GET /v1/admin/stats` — statystyki
- `GET /v1/admin/monitoring` — monitoring LLM
