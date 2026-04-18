# Frontend — React + Vite

## Stack

React 18, Vite 5, React Router 6, Tailwind CSS.

Wcześniejszy stack (Next.js 14 App Router) zastąpiony czystym SPA — brak SSR, prostsza konfiguracja, pełna kontrola nad routingiem.

## Struktura katalogów

```
frontend/
  index.html              # Punkt wejścia HTML (Vite)
  vite.config.ts           # Konfiguracja Vite + proxy /th-api → backend
  tailwind.config.ts       # Kolory: ink, paper, accent
  postcss.config.mjs
  package.json
  tsconfig.json
  .env.local               # BACKEND_INTERNAL_URL (proxy dev)
  src/
    main.tsx               # ReactDOM.createRoot + BrowserRouter
    App.tsx                 # Routing (Routes/Route)
    globals.css             # Tailwind base + dark mode
    lib/
      api.ts               # Wrapper fetch + JWT token + helpery plików
    components/
      Nav.tsx               # Nawigacja górna + wykrywanie roli admin
      ProtectedLayout.tsx   # Auth guard + Nav + Outlet (zastępuje AuthGate + layout Next.js)
    pages/
      LoginPage.tsx
      RegisterPage.tsx
      AssistantPage.tsx     # Chat z orchestratorem, wybór projektu, pliki kontekstowe
      MaterialsPage.tsx     # CRUD projektów, upload/download/eksport plików, potwierdzenia
      ProfilePage.tsx
      AdminMonitoringPage.tsx
      AdminUsersPage.tsx
```

## Routing

| Ścieżka | Komponent | Auth |
|----------|-----------|------|
| `/login` | LoginPage | nie |
| `/register` | RegisterPage | nie |
| `/assistant` | AssistantPage | tak |
| `/materials` | MaterialsPage | tak |
| `/profile` | ProfilePage | tak |
| `/admin/monitoring` | AdminMonitoringPage | tak (admin) |
| `/admin/users` | AdminUsersPage | tak (admin) |
| `*` | → redirect `/assistant` | — |

Chronione trasy owinięte `ProtectedLayout` — brak tokena JWT w `localStorage` → redirect na `/login`.

## Integracja z backendem

- **Proxy (dev):** Vite dev server przepisuje `/th-api/:path*` → `BACKEND_INTERNAL_URL/:path*` (domyślnie `http://127.0.0.1:8080`). Przeglądarka nie łączy się bezpośrednio z portem backendu — brak problemów z CORS.
- **Bezpośrednie:** opcjonalna zmienna `VITE_API_URL` (np. `http://192.168.1.5:8080`) — dla testów mobilnych lub gdy proxy jest niepotrzebne.
- **Token JWT:** `localStorage` klucz `th_token`; nagłówek `Authorization: Bearer <token>`.
- **Wrapper `api<T>()`:** generyczna funkcja fetch z automatycznym tokenem, Content-Type, obsługą 204 i błędów FastAPI (`detail`).

## Główne widoki

- **Asystent** — chat z orchestratorem; załączniki z biblioteki; tryb dry-run; historia konwersacji (sidebar). Plan: osobna zakładka **Omówienie tematu** (źródła PDF/DOCX/TXT: zapis pliku, podsumowanie + punkty LLM per plik, opcjonalnie Qdrant przy imporcie; czat z narzędziami odczytu) — [core-topic-studio.md](core-topic-studio.md).
- **Moje materiały** — projekty (CRUD), upload plików z kategorią, pobranie, eksport (PDF/DOCX/TXT), reindeksacja, usuwanie z potwierdzeniem (prepare-*/confirm).
- **Profil** — dane użytkownika z `/v1/auth/me`.
- **Admin: Monitoring** — dashboard LLM usage, incydenty, alerty, Langfuse, test webhooka.
- **Admin: Użytkownicy** — rate limit per user, reset hasła.

## Zasady UX

Jeden krok do działania, brak żargonu, domyślne wartości, progresywne ujawnianie opcji, responsywność, tryb jasny/ciemny, język PL.

## Uruchomienie (dev)

```bash
cd frontend
npm install
npm run dev       # http://127.0.0.1:18080
```

## Build produkcyjny

```bash
npm run build     # → dist/
npm run preview   # podgląd builda
```
