# Speech-to-text: ElevenLabs (Scribe) vs xAI (Grok STT)

Dokument zbiera **oficjalne informacje z dokumentacji API** (REST/WebSocket, limity, ceny). Warto przed wdrożeniem zweryfikować cenniki i limity u dostawcy.

**Uwaga:** W dokumentacji xAI pole `language` w odpowiedzi batch może być **puste** („language detection is not yet enabled”) — to istotna różnica względem ElevenLabs.

---

## xAI — Grok Speech to Text (STT)

### Produkty i endpointy

| Rodzaj | Endpoint |
|--------|----------|
| Transkrypcja pliku (batch) | `POST https://api.x.ai/v1/stt` — multipart, plik lub URL po stronie serwera |
| Streaming (realtime) | `wss://api.x.ai/v1/stt` — audio jako **surowe ramki binarne** (nie base64), konfiguracja przez parametry zapytania przy połączeniu |

**Osobno:** Voice Agent (`wss://api.x.ai/v1/realtime`) to **konwersacja głosowa z modelem** (inny produkt i cennik, np. ok. **3 USD/h** audio w dokumentacji), **nie** czyste STT.

### Cennik i limity (STT)

| Tryb | Cena | Limity (z dokumentacji) |
|------|------|-------------------------|
| REST (batch) | **0,10 USD / godz. audio** | **600 RPM**, **10 RPS** |
| WebSocket (streaming STT) | **0,20 USD / godz. audio** | **100 równoległych sesji** na zespół |

Rozliczenie według **czasu trwania audio**.

### Wejście — REST (`POST /v1/stt`)

- **`file`** — upload albo **`url`** — adres pliku do pobrania (wymagane jedno z dwóch).
- **Rozmiar pliku:** do **500 MB**.
- **Kontenery (autowykrywanie):** m.in. `wav`, `mp3`, `ogg`, `opus`, `flac`, `aac`, `mp4`, `m4a`, `mkv` (w MKV ograniczenie kodeków: MP3/AAC/FLAC).
- **Surowe formaty:** `pcm`, `mulaw`, `alaw` — wtedy wymagane **`audio_format`** + **`sample_rate`** (8–48 kHz wg enum w dokumentacji).
- **`language`** — kod języka (np. `en`, `fr`, `de`, `ja`); razem z formatowaniem włącza **Inverse Text Normalization** (mowa → zapis liczb, walut, jednostek).
- **`format`** — `true`/`false`: gdy `true`, włącza formatowanie; **wymaga ustawionego `language`**.
- **`multichannel`** — transkrypcja **per kanał**; wyniki w tablicy `channels`.
- **`channels`** — dla surowego wielokanałowego: **2–8** kanałów; dla kontenerów liczba kanałów z nagłówka pliku.
- **`diarize`** — **diaryzacja mówców**; w `words` pojawia się pole **`speaker`** (indeks 0-based).

### Wyjście — REST

- **`text`** — pełny transkrypt; przy wielu kanałach może być **złączone po czasie** między kanałami.
- **`language`** — w dokumentacji: **obecnie puste**, bo **wykrywanie języka nie jest jeszcze włączone**.
- **`duration`** — długość audio w sekundach.
- **`words`** — słowa z **`start`/`end`**, opcjonalnie **`confidence`** (0–1), opcjonalnie **`speaker`** przy diarize.
- **`channels`** — przy `multichannel=true`: osobno `index`, `text`, `words` na kanał.

### Streaming — WebSocket `wss://api.x.ai/v1/stt`

- **Audio:** ramki binarne, kodowanie z parametru **`encoding`**: `pcm` (16-bit LE), `mulaw`, `alaw`.
- **`sample_rate`:** 8000–48000 Hz (wartości z dokumentacji).
- **`interim_results`:** `true` → zdarzenia częściowe ok. **co 500 ms** (`is_final=false`); `false` — tylko finalne fragmenty.
- **`endpointing`:** cisza w ms (0–5000) przed `speech_final=true`; domyślnie **10 ms**; `0` = bez opóźnienia na granicy VAD.
- **`language`** — przy ustawieniu włącza **Inverse Text Normalization** w streamie.
- **`multichannel` + `channels` (≥2, max 8)** — audio **przeplatane** między kanałami.
- **`diarize`** — diaryzacja w eventach `transcript.partial` / zakończeniu.
- **Jedna wypowiedź na połączenie** — po zakończeniu **ponowne połączenie** dla kolejnej.
- **Przepływ:** czekaj na **`transcript.created`** zanim wyślesz audio; kończ **`audio.done`**; serwer wysyła **`transcript.done`** i zamyka połączenie.
- Zdarzenia: `transcript.partial` (interim / chunk final / utterance final przez `is_final` i `speech_final`), `transcript.done`, `error`.

### Języki

W materiałach xAI podawane jest **25+ języków** dla STT; szczegółowej listy nie ma w skróconej referencji REST — przed produkcją warto zestawić z konsolą/docs w momencie integracji.

---

## ElevenLabs — Speech to Text (Scribe)

### Modele

- **Scribe v2** — batch (wysoka dokładność), **90+ języków**, keytermy, entity detection, diaryzacja, tagowanie zdarzeń audio, timestampy słów itd.
- **Scribe v2 Realtime** — transkrypcja na żywo, deklarowana **niska latencja (~150 ms†)**, 90+ języków, timestampy słów; osobny produkt pod agenty.

### Endpointy

- **Batch:** `POST https://api.elevenlabs.io/v1/speech-to-text` (multipart).
- **Realtime:** `wss://api.elevenlabs.io/v1/speech-to-text/realtime` (oraz hosty **US**, **EU residency**, **India** — osobne adresy w dokumentacji).

### Cennik (orientacyjnie — weryfikacja: [elevenlabs.io/pricing/api](https://elevenlabs.io/pricing/api))

| Pozycja | Szacunek |
|---------|----------|
| Scribe v1/v2 (batch) | ok. **0,22 USD / h** audio |
| Opcje dodatkowe (z cennika STT) | np. entity detection ~**0,07 USD/h**, keyterm prompting ~**0,05 USD/h** |
| Scribe v2 Realtime | ok. **0,39 USD/h** (w umowach/rocznych planach często niżej, np. ~**0,28 USD/h**) |

**Dopłaty z dokumentacji OpenAPI (procent od bazy żądania):**

| Parametr | Dopłata |
|----------|---------|
| `entity_detection` | **+30%** |
| `entity_redaction` | **+30%** |
| `keyterms` | **+20%**; przy **>100 keyterms** minimalnie **20 s** rozliczenia na żądanie |
| `detect_speaker_roles` | **+10%**; wymaga `diarize=true`, nie z `use_multi_channel=true` |

### Batch — `POST /v1/speech-to-text` (najważniejsze parametry)

- **`model_id`:** `scribe_v2` lub `scribe_v1` (wymagane).
- **Źródło:** **`file`** **albo** **`cloud_storage_url`** (HTTPS, plik **< 2 GB**) **albo** **`source_url`** (m.in. **YouTube, TikTok**, hostowane audio/wideo).
- **Minimalna długość audio:** **100 ms**.
- **Rozmiar pliku:** **< 3 GB**.
- **Czas trwania:** do **10 h** (tryb standardowy); przy **`use_multi_channel=true`** — do **1 h**.
- **`language_code`** — ISO-639-1 lub ISO-639-3 lub auto (`null`).
- **`tag_audio_events`** (domyślnie `true`) — tagi typu śmiech, kroki itd.
- **`num_speakers`** — max **32** mówców (lub auto).
- **`diarize`** — diaryzacja; **`diarization_threshold`** gdy `num_speakers=null`.
- **`timestamps_granularity`:** `none` | **`word`** | **`character`**.
- **`additional_formats`** — eksport m.in. **DOCX, HTML, PDF, SRT** (wg schematu OpenAPI).
- **`file_format`:** `pcm_s16le_16` (16 kHz, mono, LE) vs `other` — przy PCM niższa latencja.
- **`use_multi_channel`** — do **5 kanałów**; **każdy kanał rozliczany jak pełny czas trwania** (koszt rośnie liniowo z liczbą kanałów).
- **`webhook` / `webhook_id` / `webhook_metadata`** — transkrypcja asynchroniczna + webhooki.
- **`temperature`**, **`seed`** — kontrola losowości / powtarzalności (seed bez gwarancji determinizmu).
- **`entity_detection`**, **`entity_redaction`**, **`entity_redaction_mode`** — wykrywanie/redakcja encji (PII, PHI, PCI itd.).
- **`keyterms`** — do **1000** fraz; max **50 znaków** na frazę; max **5 słów** po normalizacji.
- **`no_verbatim`** — tylko **scribe_v2**: usuwa fillery, fałsze starty, dźwięki niesłowne.
- **`detect_speaker_roles`** — role agent/klient (warunki jak w tabeli dopłat).

### Przykładowe wyjście (z dokumentacji)

- **`language_code`**, **`language_probability`**, **`text`**, **`words`** z **`start`/`end`**, **`type`:** `word` | `spacing` | **`audio_event`**, **`speaker_id`**.
- W dokumentacji: długa lista języków z kodami (np. polski **`pol`**) oraz pasma **WER** (polski w grupie „Excellent ≤5% WER”).

### Realtime — WebSocket

- **Autoryzacja:** nagłówek **`xi-api-key`** lub **`token`** w query (tokeny jednorazowe — do użycia po stronie klienta).
- **Parametry sesji:** `model_id`, `include_timestamps`, `include_language_detection`, **`audio_format`** (np. PCM 8–48 kHz, **ulaw_8000**), `language_code`, **`commit_strategy`:** **`manual`** vs **`vad`**, progi VAD.
- **Wiadomości:** `input_audio_chunk` z **`audio_base_64`**, **`commit`**, **`sample_rate`**, opcjonalnie **`previous_text`** — **tylko przy pierwszym chunku** (kontekst dla modelu).
- **Odpowiedzi:** m.in. `partial_transcript`, `committed_transcript`, `committed_transcript_with_timestamps` (słowa, **`logprob`**, **`speaker_id`** gdy dostępne).
- **`enable_logging=false`** — tryb zbliżony do **zero retention**; w dokumentacji: **tylko enterprise**.

### Zgodność i dane

- **HIPAA:** wymaga **BAA** przez **Sales** przed wdrożeniami medycznymi.
- **Rezydencja danych:** osobne endpointy **EU** / **India** w dokumentacji realtime.

### Wydajność batch (równoległość)

Przy plikach **> 8 min** wewnętrznie chunkowanie i równoległa transkrypcja (do **4** segmentów) — w dokumentacji podany wzór na concurrency w zależności od długości nagrania.

---

## Zestawienie bezpośrednie

| Aspekt | xAI Grok STT | ElevenLabs Scribe |
|--------|----------------|-------------------|
| **Batch vs stream** | REST + osobny WS STT | REST batch + osobny WS realtime |
| **Cena (z cenników)** | **0,10 USD/h** batch, **0,20 USD/h** stream | **~0,22 USD/h** batch; realtime **~0,39 USD/h** (+ opcje i dopłaty %) |
| **Max plik / czas** | **500 MB** | **3 GB**; **10 h** (1 h przy multi-channel) |
| **Źródło URL** | **`url`** do pliku audio | HTTPS do 2 GB; **YouTube/TikTok** (`source_url`) |
| **Wielokanał** | **2–8** kanałów | **do 5**; osobne rozliczenie per kanał |
| **Diaryzacja** | Tak (`diarize`) | Tak + **do 32** mówców; **role agent/customer** (dopłata) |
| **Język w odpowiedzi** | Pole `language` w batch może być **puste** (detekcja „not yet enabled” w docs) | **`language_code` + probability**, lista 90+ języków, WER per język |
| **ITN / formatowanie liczb** | **`format` + `language`** (batch i stream) | Osobne funkcje (encje, keytermy, redakcja itd.) |
| **Timestampy** | Poziom słowa (`start`/`end`) | **word** lub **character**; realtime opcjonalnie |
| **Niestandardowe słownictwo** | Nie opisane w skrócie STT | **Keyterms** (do 1000, dopłata %) |
| **Encje / PII** | Nie w tym samym sensie co EL | **entity_detection** / **redaction** (dopłata %) |
| **Zdarzenia niewerbalne** | — | **`tag_audio_events`**, typ `audio_event` |
| **Eksport dokumentów** | — | **DOCX/HTML/PDF** przez `additional_formats` |
| **Webhooki async** | — | Tak |
| **Streaming audio do STT** | Surowe bajty PCM/μ-law/A-law | Base64 w chunkach (`input_audio_chunk`) |
| **Sesja stream** | Jedna wypowiedź na połączenie | Konfiguracja VAD/manual commit, regiony EU/US/IN |

---

## Werdykt (skrót)

- **xAI:** prosty **cennik za godzinę**, **REST z URL**, **wielokanał 2–8**, **ITN** przy ustawionym języku, stream z **surowym PCM**; uwaga na **wykrywanie języka w batch** (pole `language` w dokumentacji może być puste).
- **ElevenLabs:** **szerszy zestaw funkcji** (encje, keytermy, role, webhooks, YouTube, eksporty, residency), **języki i WER opisane szerzej**, realtime z **tokenami klienta** i wieloma regionami — przy **wyższej złożoności ceny** (dopłaty procentowe i osobna stawka realtime).

---

## Źródła do weryfikacji

- xAI: [Voice — REST API Reference](https://docs.x.ai/developers/rest-api-reference/inference/voice), [Models and Pricing](https://docs.x.ai/docs/models)
- ElevenLabs: [Speech to Text capabilities](https://elevenlabs.io/docs/capabilities/speech-to-text), [API — Create transcript](https://elevenlabs.io/docs/api-reference/speech-to-text/convert), [Realtime STT](https://elevenlabs.io/docs/api-reference/speech-to-text), [API pricing](https://elevenlabs.io/pricing/api)
