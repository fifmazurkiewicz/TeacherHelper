# Zasady i wymagania — Asystent Nauczyciela AI

Źródło: analiza projektu wersja 4.0 (kwiecień 2026), plik `analiza_projektu_v4.docx`.

Szczegółowe opisy komponentów: [komponenty/README.md](komponenty/README.md).  
**Omówienie tematu (NotebookLM-like):** [komponenty/core-topic-studio.md](komponenty/core-topic-studio.md).

---

## 1. Cele i zakres produktu

- **Cel główny:** prosty asystent AI generujący materiały edukacyjne z opisu celu, przechowujący pliki i umożliwiający rozmowę o wcześniej utworzonych materiałach.
- **Omówienie tematu:** osobny flow „jak NotebookLM” — **nowy temat** → **wiele plików źródłowych (PDF, Word, TXT)** → przy **każdym wgrywaniu:** **zapis pliku w aplikacji**, ekstrakcja tekstu, **LLM: krótkie podsumowanie + najważniejsze punkty** przy pliku, **opcjonalnie Qdrant** (indeks chunków przy imporcie) → **dedykowany czat** z LLM nad tematem; w czacie **narzędzia** (lista, metadane z podsumowaniem, odczyt fragmentów), ewentualnie wyszukiwanie semantyczne. Szczegóły: [core-topic-studio.md](komponenty/core-topic-studio.md).
- **Narzędzie darmowe** — dostępne wyłącznie dla wybranych osób (bez planów subskrypcyjnych).
- **Konwersacja celowa:** użytkownik opisuje *co* chce osiągnąć; system dobiera moduły przez tool calling (narzędzia LLM), planuje i wykonuje.
- **Kontekst plików:** odczyt i rozumienie wygenerowanych plików (scenariusze, piosenki, prezentacje); modyfikacje, porównania, rozszerzenia.
- **Eksport wieloformatowy:** DOCX, PDF, TXT, PPTX (zgodnie z typem treści); w przyszłości PNG, MP4, SVG, GIF.
- **Baza plików:** organizacja, wersjonowanie, udostępnianie na konto.
- **UX:** użytkownik nietechniczny — minimum kroków do rezultatu.
- **Architektura:** Clean Architecture, modularność, **tool calling** w orchestratorze. Integracje zewnętrzne (np. generacja audio przez Suno) jako **API lub gotowe usługi** — TeacherHelper **nie jest** serwerem MCP; opcjonalnie może **korzystać** z zewnętrznych narzędzi jako klient aplikacyjny.
- **Deployment:** cloud-native, CI/CD, Infrastructure as Code.

---

## 2. Przepływ konwersacyjny (tool calling)

1. Analiza intencji — LLM decyduje które narzędzia wywołać (ask_clarification, generate_scenario, itp.).
2. Dopytywanie — gdy brakuje informacji, LLM wywołuje `ask_clarification`.
3. Generowanie — LLM wywołuje odpowiednie narzędzia (`generate_scenario`, `generate_music`, itp.).
4. Zapis do bazy plików konta.
5. Eksport do wybranego formatu.

**Inteligentne dopytywanie:** brak wieku → pytanie o grupę; niejasny format → doprecyzowanie; sugestie rozszerzeń.

---

## 3. Moduły generowania treści (wymagania funkcjonalne)

| Moduł | Zakres | Formaty (przykłady) |
|--------|--------|---------------------|
| Scenariusze | Postacie, dialogi, didaskalia, reżyseria, sceny | DOCX, PDF |
| Grafiki | Scena, kostiumy, plakaty, zaproszenia | PNG, JPG, PDF, SVG |
| Muzyka | Prompty (Suno/MusicGen/Udio), styl, tempo | TXT, DOCX, PDF |
| Wiersze | Recytacje, forma, długość, głosy | PDF, DOCX, TXT |
| Wideo | Krótkie formy, animacje, instruktaże | MP4, GIF, MOV |
| Prezentacje | Z tematu / obszaru / scenariusza | PPTX, PDF, PNG |

---

## 4. Baza plików i kontekst (Files Context)

- **Struktura:** projekty (foldery), **tematy omówienia** (zestaw plików źródłowych + czat z narzędziami odczytu; RAG opcjonalnie), kategorie (Scenariusze, Grafiki, Wideo, Muzyka, Wiersze, Prezentacje), wersje plików, pliki poza projektami.
- **Widoki:** kafelki, lista, wyszukiwarka pełnotekstowa.
- **Metadane:** nazwa, typ, format, projekt, wersja, tagi, status (np. robocza/zatwierdzona).
- **Operacje:** pobierz, konwertuj, edytuj, duplikuj, archiwizuj, eksport ZIP.
- **Kontekst dla LLM:** indeksowanie → wyszukiwanie semantyczne (Qdrant + OpenAI embeddings) → załadowanie fragmentów do kontekstu → operacje (podsumowanie, zmiana, porównanie) → zapis jako nowa wersja.

**Bezpieczeństwo kontekstu:** izolacja per użytkownik; audyt odczytów przez AI; limit kontekstu (fragmenty, nie zawsze całość); brak trwałej persystencji treści plików w modelu.

**Ekstrakcja treści (odczyt):** DOCX (python-docx/Pandoc), PDF (PyMuPDF/pdfplumber), PPTX (python-pptx), TXT, obrazy (opis vision), MP4 (transkrypcja + klatki), SVG (XML).

---

## 5. Architektura — zasady obowiązkowe

### 5.1. Clean Architecture — warstwy

| Warstwa | Odpowiedzialność | Przykłady |
|---------|------------------|-----------|
| **Domain** | Logika biznesowa, encje, reguły; zero zależności od frameworków | User, Project, FileAsset, Topic (omówienie tematu), ScenarioSpec, PresentationSpec, Poem, MusicPrompt |
| **Use Cases** | Orkiestracja akcji; zależność tylko od Domain | GenerateScenario, CreatePresentation, ReadFileContext, ExportProject, AnalyzeIntent, TopicSourcesChat (plan) |
| **Interface Adapters** | Mapowanie Use Cases ↔ świat zewnętrzny | REST, DTO, CLI |
| **Infrastructure** | Bazy, API zewnętrzne, storage, auth — wymienne | PostgreSQL, Qdrant, Redis, S3, OpenRouter |

### 5.2. Zasady projektowe

- **Dependency Rule:** zależności wyłącznie do wewnątrz: Infrastructure → Adapters → Use Cases → Domain.
- **Dependency injection:** use casey zależą od interfejsów, nie od konkretnej bazy.
- **Port/Adapter:** każda integracja zewnętrzna za portem (np. zamiana DALL-E na Midjourney = wymiana adaptera).
- **Tool calling:** orchestrator deleguje akcje przez narzędzia LLM, nie przez sztywny pipeline wyłącznie po stronie kodu.
- **Single responsibility:** osobny use case i adapter AI na moduł.

### 5.3. Modular monolith

- Jeden deployment, wyraźne granice modułów (`domain`, `use_cases`, `adapters` per obszar).
- Możliwość późniejszej ekstrakcji modułu do osobnej usługi.

---

## 6. Stack technologiczny

- **Frontend:** React 18 + Vite + React Router 6, Tailwind CSS.
- **Backend API:** FastAPI (Python).
- **Orkiestrator AI:** Tool calling (OpenAI-compatible function calling) — LLM decyduje które narzędzia uruchomić.
- **Wyszukiwanie semantyczne:** Qdrant (wektory) + OpenAI Embeddings (`text-embedding-3-small`).
- **LLM:** OpenRouter (domyślnie GPT-4o-mini) / Claude API (Sonnet/Opus) — intencje, generowanie, praca na plikach.
- **Baza:** PostgreSQL; cache/rate-limiting: Redis.
- **Storage plików:** S3 / R2 / GCS (dev: dysk lokalny).
- **Auth:** JWT (email+hasło).
- **Eksport:** python-docx (DOCX), fpdf2 (PDF), python-pptx (PPTX).

---

## 7. Cloud-native i DevOps

- Hosting (docelowo): frontend SPA + backend na **GCP** (np. Compute Engine, Cloud SQL); wektory — **Qdrant Cloud** lub równoważny hosting; pliki `deploy/gcp/`.
- Docker na VM; ewentualnie później Cloud Run — poza zakresem obecnych plików Compose w repo.
- Monorepo, GitHub Actions (test, lint, build, deploy), preview na PR, trunk-based development.
- Migracje: Alembic.
- Rollback < 60 s.
- Bezpieczeństwo: TLS, szyfrowanie at rest, secrets manager, WAF, rate limiting, backup.

---

## 8. UX — zasady

- Jeden krok do działania: od razu pole wpisu (bez zbędnych wizardów).
- Język dla nauczycieli (np. „Moje materiały", nie żargon techniczny).
- Domyślne sensowne; zaawansowane pod „Więcej opcji".
- Pierwszy materiał < 60 s od rejestracji (cel).
- Jasne „co dalej"; cofnij / regeneruj / edytuj.
- Chat główny + panel „Moje materiały" (przeciąganie plików do czatu).
- Onboarding: e-mail+hasło; kafelki przykładów; krótki tutorial.
- Nawigacja: Asystent | **Omówienie tematu** | Moje materiały | Profil (zwięzła nawigacja, max ~2 kliki do kluczowych akcji).
- Dostępność: responsywność, WCAG 2.1 AA, tryb jasny/ciemny, język PL.

---

## 8a. Omówienie tematu — flow biznesowy (streszczenie)

1. Użytkownik tworzy **nowy temat** (nazwa, opcjonalny opis).
2. W ramach tematu **wgrywa jeden lub wiele plików** naraz: **PDF**, **Word (DOCX)**, **TXT**.
3. Dla **każdego** pliku: **zapis w aplikacji** (storage + metadane pod tematem), **ekstrakcja tekstu**, **LLM generuje krótkie podsumowanie i listę najważniejszych punktów** (utrwalone przy pliku, widoczne w UI); **opcjonalnie** równolegle **indeks wektorowy w Qdrant** (chunki tego pliku w kontekście tematu).
4. Po zakończeniu przetwarzania użytkownik **rozmawia z LLM** w oknie czatu nad tematem; model korzysta z **narzędzi** (lista plików, metadane z podsumowaniem, odczyt treści/fragmentu) i ewentualnie **wyszukiwania semantycznego**, jeśli Qdrant jest włączony.
5. Asystent (generowanie scenariuszy, grafik itd.) pozostaje **osobnym** obszarem produktu; można później rozważyć mostki (np. „wygeneruj materiał na podstawie tematu”).

Pełny opis: [komponenty/core-topic-studio.md](komponenty/core-topic-studio.md).

---

## 9. Konta, role

- **Role:** Nauczyciel (tworzenie, baza, eksport); Administrator (platforma, limity, moderacja, logi).
- **Logowanie:** e-mail+hasło.
- **Dostęp:** narzędzie darmowe, wyłącznie dla zaproszonych osób (admin zarządza kontami).

---

## 10. Panel administracyjny

Dashboard (użytkownicy, zużycie API, storage, koszty, alerty), CRUD kont, moderacja, konfiguracja limitów (per user) i modeli, resetowanie haseł, raporty.

---

## 11. Checklist dla implementacji

- [x] Warstwy Domain → Use Cases → Adapters → Infrastructure bez naruszenia Dependency Rule.
- [x] Porty dla: storage, repo metadanych, LLM (tool calling), embeddingi (OpenAI).
- [x] Izolacja `user_id` przy każdym odczycie pliku i zapytaniu do wektorów.
- [x] Logowanie audytowe odczytów plików przez AI.
- [x] Rate limiting na endpointach generowania (Redis + fallback in-memory).
- [x] Konfiguracja przez zmienne środowiskowe (bez sekretów w repozytorium).
- [x] Eksport plików (TXT, PDF, DOCX, PPTX).
- [x] Wyszukiwanie wektorowe (Qdrant).
- [x] Tool calling zamiast JSON pipeline w orchestratorze.
- [x] Security headers middleware.
- [x] Porty dla: grafika, wideo (ImageGeneratorPort, VideoGeneratorPort + adapter DALL-E 3).
- [x] CORS — backend czyta `CORS_ORIGINS` z `.env`; `expose_headers` dla `Content-Disposition`.
- [x] Frontend przepisany z Next.js na React 18 + Vite + React Router 6 (SPA).
- [ ] Testy jednostkowe i integracyjne.
- [ ] CI/CD pipeline (GitHub Actions).
- [ ] Dockerfiles dla backendu i frontendu.
- [ ] Zakładka **Omówienie tematu**: encja tematu, multi-upload PDF/DOCX/TXT, **zapis każdego pliku**, **podsumowanie + kluczowe punkty (LLM) per plik**, opcjonalnie **Qdrant przy imporcie**, czat z **narzędziami** list/read/metadata (i ewentualnie search) ograniczonymi do plików tematu.

---

*Dokument roboczy — utrzymywany wraz z rozwojem kodu.*
