# Analiza modeli i cen: muzyka / piosenki (MiniMax · KIE Suno · ElevenLabs · OpenRouter)

Dokument zbiera publiczne informacje o **najmocniejszych modelach** i **wycenie** pod scenariusz: piosenka z własnym promptem, stylem i tekstem (np. materiały edukacyjne). Ceny w **USD** tam, gdzie podaje je dostawca; KIE rozlicza **kredyty** — przeliczenie na walutę zależy od pakietu na koncie.

---

## 1. MiniMax przez WaveSpeedAI

Źródła: dokumentacja WaveSpeed dla poszczególnych endpointów.

| Model | Rola (wg dokumentacji) | Cena (tabela „Pricing”) | Limity tekstu / stylu (API) |
|--------|-------------------------|-------------------------|-----------------------------|
| [MiniMax Music 2.6](https://wavespeed.ai/docs/docs-api/minimax/minimax-music-2-6) | Najnowsza generacja: prompt + tekst; do **5 min** | **0,15 USD / utwór** | Tekst **10–3000** znaków; prompt do **2000** znaków |
| [MiniMax Music 2.5](https://wavespeed.ai/docs/docs-api/minimax/minimax-music-2-5) | Pełniejsza generacja (poprzednia generacja względem 2.6) | **0,15 USD / utwór** | (ta sama linia produktowa co 2.6 — szczegóły w docs) |
| [MiniMax Music 02](https://wavespeed.ai/docs/docs-api/minimax/minimax-music-02) | MoE, szybko i tanio; **wymagane** `prompt` + `lyrics` | **0,03 USD / uruchomienie** | Tekst **10–3000** znaków |
| [MiniMax Music 01](https://wavespeed.ai/docs/docs-api/minimax/minimax-music-01) | Tekst + opcjonalne referencje (utwór / głos / instrumental) | **0,35 USD / piosenka** | W tabeli API: `lyrics` ok. **350–400** znaków — mało na pełną piosenkę |

**Rekomendacja jakości vs koszt (WaveSpeed):**

- **Najwyższa jakość + długi tekst:** **Music 2.6** — **0,15 USD** za utwór (do 5 min wg opisu).
- **Najniższy koszt przy sensownym limicie tekstu:** **Music 02** — **0,03 USD**.

**Integracja z TeacherHelper:** brak gotowego adaptera WaveSpeed dla muzyki w repozytorium — wymagałaby nowej ścieżki (submit + polling wyniku).

---

## 2. KIE — Suno API

Źródła: [Suno API Quickstart](https://docs.kie.ai/suno-api/quickstart), [Generate Music (OpenAPI)](https://docs.kie.ai/suno-api/generate-music), strona [kie.ai/suno-api](https://kie.ai/suno-api).

### Modele (wybór „top”)

| Model | Kiedy (wg opisów KIE) |
|--------|------------------------|
| **V5_5** | Personalizacja / „Unleash Your Voice”, custom models dopasowane do gustu |
| **V5** | Szybsza generacja, lepsza musicalność, do **8 min** |
| **V4_5PLUS** | W sekcji *Model Selection*: **najwyższa jakość** i długie utwory |
| **V4_5ALL** | „Smart and fast” |
| **V4** | Priorytet **wokalu**; do **4 min** |

### Limity pod `customMode: true` (skrót)

- **V4:** `prompt` do 3000 znaków, `style` do 200  
- **V4_5 / V4_5PLUS / V4_5ALL / V5 / V5_5:** `prompt` do **5000**, `style` do **1000**  
- **Tytuł:** max **80** znaków  

W trybie z wokalem dokumentacja KIE traktuje `prompt` jako **tekst śpiewany** (słowa do utworu).

### Wycena

- W OpenAPI **nie ma rozdzielenia kosztu w USD per model** (V4 vs V5 vs V5_5) dla `POST /api/v1/generate`.
- Rozliczenie: **kredyty**; przy braku środków kod **402** (*Insufficient Credits*).
- **Przelicznik pakietu (orientacyjny):** przy typowej ofercie doładowań KIE przyjmuje się ok. **1000 kredytów = 5 USD** — ułatwia szacunek kosztu jednej generacji, jeśli znasz cenę w kredytach (dokładna stawka zależy od wybranego pakietu i promocji na koncie).
- Na stronie produktu przy **różnych** operacjach pojawiają się różne wartości w kredytach (np. **0,5** vs **12**) — dotyczą one **różnych endpointów / akcji**, nie zawsze czystego „generate”. **Orientacyjna wycena w PLN/USD:** tylko z panelu KIE (pakiet kredytów + test jednego żądania).

#### Tabela operacji Suno w panelu KIE (kredyty / gen + „Our Price” USD)

Poniżej: **widok cenowy** z panelu KIE dla usług oznaczonych jako **Suno** (kolumny m.in. *Credits / Gen* i *Our Price*). **Źródło:** zrzut z panelu (kwiecień 2026). W tabeli źródłowej kolumny *Fal Price* i *DISCOUNT* były puste (N/A) — pominięte tutaj.

**Uwaga:** to jest **rozliczenie per typ akcji** (np. *Generate Music*, *Extend Music*), a **nie** jawny podział „V4 vs V5 vs V4_5ALL” w jednym wierszu — nadal nie wiadomo z samej tabeli, czy wybór `model` w `POST /api/v1/generate` zmienia liczbę kredytów przy tej samej etykiecie „Generate Music”.

| Operacja (wg etykiety w panelu) | Kredyty / gen | Cena „Our Price” (USD) |
|--------------------------------|---------------:|----------------------:|
| Boost Music Style Boost | 0,4 | 0,002 |
| Generate sounds | 2,5 | 0,0125 |
| Mashup | 12 | 0,06 |
| Replace Music Section | 5 | 0,025 |
| Multi-Stem Separation | 50 | 0,25 |
| Vocal Separation | 10 | 0,05 |
| convert-to-wav-format | 0,4 | 0,002 |
| Generate Lyrics | 0,4 | 0,002 |
| upload-and-cover-audio | 12 | 0,06 |
| create-music-video | 2 | 0,01 |
| upload-and-extend-audio | 12 | 0,06 |
| add-instrumental | 12 | 0,06 |
| **Generate Music** | **12** | **0,06** |
| Extend Music | 12 | 0,06 |
| add-vocals | 12 | 0,06 |

Przelicznik w tej tabeli jest spójny z przyjętym wyżej szacunkiem **~1000 kredytów ≈ 5 USD** (np. **12 kredytów ≈ 0,06 USD** na jedną generację typu *Generate Music*).

### V4_5ALL vs pozostałe modele KIE — czy jest różnica cenowa?

W **publicznej** specyfikacji [`generate-music`](https://docs.kie.ai/suno-api/generate-music) widać **enum modeli** i **limity** (`prompt` / `style`, maks. długość utworu), ale **brak tabeli „zużycie kredytów na jedno `generate`” z podziałem na V4, V4_5ALL, V5 itd.** Z samego OpenAPI **nie da się** więc stwierdzić, czy **V4_5ALL** kosztuje mniej, tyle samo czy więcej niż np. **V5** czy **V4_5PLUS** — ewentualna różnica (jeśli w ogóle istnieje) wychodzi dopiero z **historii konta / rozliczeń** po realnym żądaniu albo z materiałów handlowych na [kie.ai](https://kie.ai/) (mogą się zmieniać).

| Aspekt | V4_5ALL | V5 / V5_5 / V4_5PLUS / V4 (skrót) |
|--------|---------|-------------------------------------|
| **Cena w kredytach per `generate` (jawna w docs)** | **Nie podana** osobno | **Nie podana** osobno |
| **Limity custom (wg docs)** | `prompt` do **5000**, `style` do **1000**, do **8 min** | **V4:** `prompt` **3000**, `style` **200**, do **4 min**; **V4_5 / V4_5PLUS / V5 / V5_5:** jak V4_5ALL (**5000** / **1000**), do **8 min** (V4 do 4 min) |
| **Rola marketingowa (wg opisów KIE)** | „Smart and fast” | V5: szybsza generacja / musicalność; V4_5PLUS: „najwyższa jakość”; V4: nacisk na wokal |

**Wniosek porównawczy:** wybór **V4_5ALL** vs innego modelu w KIE to dziś głównie **jakość / zachowanie modelu i limity tekstu**, a **nie** twardy, publiczny argument cenowy z dokumentacji API. Żeby **porównać z Lyrią w USD**, trzeba **zmierzyć** u siebie: saldo kredytów przed i po jednym `generate` dla wybranego modelu → przeliczyć na USD wg własnego pakietu (np. przy **1000 kredytów ≈ 5 USD**: koszt ≈ **(Δ kredytów / 1000) × 5 USD** — tylko przykład, **Δ** musi pochodzić z panelu).

**Integracja z TeacherHelper:** adapter `KieMusicGenerator` w `backend/teacher_helper/infrastructure/music_kie.py`; wymagany m.in. publiczny **`callBackUrl`** (`KIE_MUSIC_CALLBACK_URL`).

---

## 3. ElevenLabs — Eleven Music

Źródła: [Modele API](https://elevenlabs.io/docs/models), [cennik API](https://elevenlabs.io/pricing/api).

| Id modelu | Nazwa | Wycena |
|-----------|--------|--------|
| **`music_v1`** | **Eleven Music** — muzyka z promptu naturalnego języka | **0,30 USD za minutę** wygenerowanej muzyki |
| | | Limit długości: **do 5 min** na generację (wg strony cennika API) |
| | | Jakość: 44,1 kHz, 128–192 kbps (wg strony) |

**Przykłady:**

| Długość | Koszt (przy 0,30 USD/min) |
|---------|---------------------------|
| 1 min | 0,30 USD |
| 3 min | 0,90 USD |
| 5 min (max) | 1,50 USD |

**Uwaga:** to nie jest ten sam model pracy co KIE „wklej cały tekst jako lyrics” — Eleven Music steruje się głównie **opisem** (gatunek, nastrój, instrumenty, struktura).

**Integracja z TeacherHelper:** brak gotowej integracji Eleven Music w backendzie.

---

## 4. OpenRouter — generacja muzyki (Google Lyria 3) i kontekst wideo z audio

Źródła: karty modeli na [openrouter.ai](https://openrouter.ai/) (opis, **Pricing**, zakładka **API**).

Na OpenRouter **dedykowane generowanie muzyki** (utwory / klipy stereo z promptu tekstowego lub obrazu) jest w praktyce zdominowane przez rodzinę **Google Lyria 3** (Gemini API przez OpenRouter). Inne ścieżki audio na platformie (np. **audio output** w modelach mówionych, transkrypcja) dotyczą głównie mowy / analizy — **nie zastępują** scenariusza „pełna piosenka z refrenem” jak Lyria czy Suno.

### Top 3 (wg dopasowania do tego dokumentu: muzyka / materiały dźwiękowe)

| # | Id modelu (OpenRouter) | Rola | Cena (wg karty OpenRouter) | Dlaczego w „top 3” |
|---|------------------------|------|----------------------------|---------------------|
| **1** | **`google/lyria-3-pro-preview`** | Pełne utwory: zwrotki, refreny, mostki; audio **48 kHz** stereo; prompt tekstowy lub obraz; spójność strukturalna, wokal, **tekst zsynchronizowany z czasem** (wg opisu Google / OpenRouter) | **0,08 USD / utwór** (*per song*) | **Najlepszy stosunek jawnej ceny do pełnej piosenki** względem MiniMax 2.6 (0,15 USD) i Eleven Music (0,30 USD/min — przy typowej długości utwór Lyria bywa taniej w przeliczeniu na „jedną piosenkę”). |
| **2** | **`google/lyria-3-clip-preview`** | Krótkie fragmenty (~**30 s**): pętle, zajawki, szybkie iteracje stylu | **0,04 USD / klip** (*per clip*) | **Najniższy koszt eksperymentu** przy tej samej rodzinie modeli co Pro — sensowny wybór zanim „spalisz” budżet na pełnym utworze. |
| **3** | **`google/veo-3.1`** | **Wideo** 720p/1080p/4K z **natywnie zsynchronizowanym audio** (dialog, ambient, tło — wg opisu); *nie* jest to zamiennik eksportu samego MP3 jak Lyria | **od ~0,40 USD / sekundę** (720p/1080p **z audio**); **~0,60 USD / s** przy 4K z audio; tańsze warianty **bez audio** (np. ~0,20 USD/s przy 720p/1080p) | **Trzeci sensowny punkt na OpenRouterze, gdy celem jest klip audiowizualny** (np. scenka z lektorem / dźwiękiem sceny), a nie czysty plik muzyczny. Dla samej piosenki edukacyjnej nadal wybieraj **Lyria Pro** lub **Clip**. |

**Parametry techniczne (wspólne dla obu Lyria 3 Preview, wg kart modeli):** bardzo duży kontekst (**~1 048 576** tokenów), **max output** rzędu **~65,5K** — przy muzyce rozliczenie użytkownika jest jednak nadrzędnie **per song / per clip**, a nie klasycznie „per 1M tokenów” (tokenowe ceny na stronie traktować jako informację techniczną / uśrednienia między dostawcami).

**API (Lyria):** zgodne z **OpenAI-compatible** `POST /api/v1/chat/completions`, pole `model` + `messages` (multimodalny content: tekst / obraz). Szczegóły: [Lyria 3 Pro — API](https://openrouter.ai/google/lyria-3-pro-preview/api), [Lyria 3 Clip — API](https://openrouter.ai/google/lyria-3-clip-preview/api).

**API (Veo 3.1):** osobna ścieżka **generacji wideo** na OpenRouter (żądanie + polling statusu); model eksperymentalny / **alpha** — przed produkcją warto sprawdzić aktualne ograniczenia w dokumentacji OpenRouter.

**Uwaga o wersji datowanej:** na stronie może pojawić się alias typu `google/lyria-3-pro-preview-20260330` — to ta sama linia **Lyria 3 Pro Preview**; canonicalny identyfikator w przykładach API to zwykle **`google/lyria-3-pro-preview`**.

**Integracja z TeacherHelper:** brak produkcyjnego adaptera Lyria w głównym backendzie; odniesienie implementacyjne: `research/music-provider-benchmark/benchmark/openrouter_media.py` (Lyria przez `chat/completions`).

---

## 5. Zestawienie porównawcze

| Dostawca | Model „top” / rekomendowany | Koszt (jawne USD) | Długi własny tekst + styl |
|----------|----------------------------|-------------------|---------------------------|
| WaveSpeed / MiniMax | **Music 2.6** | **0,15 USD / utwór** | Tak (do 3000 znaków tekstu + prompt) |
| WaveSpeed / MiniMax | **Music 02** | **0,03 USD / run** | Tak (10–3000 znaków + wymagany prompt) |
| WaveSpeed / MiniMax | **Music 01** | **0,35 USD / utwór** | Raczej nie (bardzo krótki limit `lyrics` w API) |
| KIE / Suno | **V4_5ALL**, **V5_5**, **V5**, **V4_5PLUS**, **V4** itd. | **Kredyty** — w OpenAPI `generate` **brak** jawnej tabeli „kredytów per model”; w **panelu KIE** widać m.in. **12 kredytów (~0,06 USD)** na *Generate Music* / *Extend Music* itd. (szczegóły w tabeli powyżej) — **różnica V4_5ALL vs V5 w kredytach nadal nie wynika z publicznej dokumentacji** | Tak dla większości topowych (5000 / 1000; V4: 3000 / 200) |
| ElevenLabs | **`music_v1`** (Eleven Music) | **0,30 USD × minuty** | Opisowo (prompt), nie „śpiewaj dokładnie tego pliku tekstu” jak w KIE custom |
| **OpenRouter / Google** | **Lyria 3 Pro** (`google/lyria-3-pro-preview`) | **0,08 USD / utwór** (*per song*, jawna stawka na karcie OpenRouter) | Tak w praktyce (długi prompt w `messages`; limity zależą od API — w benchmarku użyto m.in. ~8000 znaków na fragment tekstu w treści user) |
| **OpenRouter / Google** | **Lyria 3 Clip** (`google/lyria-3-clip-preview`) | **0,04 USD / ~30 s** (*per clip*) | Krótki fragment — do prototypów; w **UI benchmarku** w repozytorium model Clip jest **wyłączony z listy wyboru** (nadal dostępny bezpośrednio przez API OpenRouter) |
| **OpenRouter / Google** | **Veo 3.1** (`google/veo-3.1`) | **~0,40 USD/s** (1080p z audio) | Scenariusz **wideo+dźwięk**, nie czysty tekst piosenki jak w KIE |

### Lyria 3 Pro vs KIE (Suno) — ujęcie cenowe

- **Lyria 3 Pro** na OpenRouter: **stała, jawna** stawka **0,08 USD za utwór** (*per song*) przy pełnej piosence — łatwo budżetować i porównywać z **MiniMax 0,15 USD/utwór** czy **ElevenLabs 0,30 USD/min**.
- **KIE / Suno:** w panelu KIE widać **kotwicę** dla typowej generacji (**np. 12 kredytów ≈ 0,06 USD** przy *Generate Music* — tabela w sekcji 2), ale **nie ma** w publicznym API jawnego „V4 kosztuje X, V5 kosztuje Y”. **Porównanie z Lyrią w PLN/USD** nadal warto **zweryfikować pomiarem** (saldo przed/po) przy wybranym `model`, bo różnica między wariantami Suno w kredytach **nie wynika** z samej dokumentacji OpenAPI.

---

## 6. Linki

- MiniMax Music 01: https://wavespeed.ai/docs/docs-api/minimax/minimax-music-01  
- MiniMax Music 02: https://wavespeed.ai/docs/docs-api/minimax/minimax-music-02  
- MiniMax Music 2.5: https://wavespeed.ai/docs/docs-api/minimax/minimax-music-2-5  
- MiniMax Music 2.6: https://wavespeed.ai/docs/docs-api/minimax/minimax-music-2-6  
- KIE Suno — quickstart: https://docs.kie.ai/suno-api/quickstart  
- KIE — generate music: https://docs.kie.ai/suno-api/generate-music  
- ElevenLabs — modele: https://elevenlabs.io/docs/models  
- ElevenLabs — cennik API: https://elevenlabs.io/pricing/api  
- OpenRouter — Lyria 3 Pro Preview: https://openrouter.ai/google/lyria-3-pro-preview  
- OpenRouter — Lyria 3 Clip Preview: https://openrouter.ai/google/lyria-3-clip-preview  
- OpenRouter — Veo 3.1: https://openrouter.ai/google/veo-3.1  

---

## 7. Jednorazowy benchmark (osobny projekt)

Porównanie MP3 / wideo + trace dla KIE / WaveSpeed MiniMax / OpenRouter (Lyria — wiele modeli z katalogu, Seedance) oraz opcjonalnie **ElevenLabs Music**: folder **`research/music-provider-benchmark/`** (własny `uvicorn`, nie jest częścią backendu TeacherHelper). Flow: **`GET /api/model-catalog`** → **`/api/preview`** (edycja JSON) → **`/api/run`** (wysyłka).

---

*Dokument ma charakter informacyjny; ceny i limity mogą się zmienić u dostawcy — przed wdrożeniem warto zweryfikować aktualne strony.*
