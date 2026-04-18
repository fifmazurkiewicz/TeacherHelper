# Music provider benchmark (research)

Samodzielny, **jednorazowy** mini-projekt: to samo wejście (styl, słowa, tytuł) → równoległe wywołania (**KIE Suno**, **MiniMax przez WaveSpeed**, **OpenRouter Lyria** — jeden lub wiele modeli z katalogu Lyria, **OpenRouter Seedance 1.5 Pro**, opcjonalnie **ElevenLabs Music** `POST /v1/music`) → odpowiedź JSON z **`trace`** oraz **`artifacts`** (audio/wideo, base64 lub link CDN).

Nie jest częścią backendu TeacherHelper — nie uruchamia się z głównego `uvicorn teacher_helper`.

## Wymagania

- Python 3.11+
- Klucze API: `KIE_API_KEY`, `KIE_MUSIC_CALLBACK_URL`, `WAVESPEED_API_KEY`, `OPENROUTER_API_KEY` (Lyria + Seedance)
- Opcjonalnie: `ELEVENLABS_API_KEY` — wtedy w UI możesz dodać wiersz „ElevenLabs — Music API” i uruchomić **Eleven Music** równolegle z innymi dostawcami

## Uruchomienie

```bash
cd research/music-provider-benchmark
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy .env.example .env
# uzupełnij .env
uvicorn benchmark.main:app --host 127.0.0.1 --port 8765
```

Otwórz w przeglądarce: **http://127.0.0.1:8765/**.

### Dwuetapowy flow

1. **`GET /api/model-catalog`** — listy modeli do formularza: **KIE Suno**, **WaveSpeed** (`music-2.6` / `music-02`), OpenRouter **Lyria** (`GET …/models`, max **10**; przy braku klucza — fallback), OpenRouter **wideo (Seedance)** — statyczna lista, ElevenLabs Music (`music_v1`).
2. **`POST /api/preview`** — z formularza + **wierszy „Dodaj model”** buduje **listę** `kie_jsons`, **listę** `wavespeed_jobs` (każdy: `variant` + `wavespeed_json`), `openrouter_music_jsons`, `elevenlabs_jsons`, **`openrouter_seedance_jsons`** (tylko gdy są wiersze `openrouter_video`) oraz mapowania i URL-e. **Bez** wywołań do zewnętrznych API.
3. W UI edytujesz wygenerowane JSON-y (np. dopracowanie promptu).
4. **`POST /api/run`** — wysyła zatwierdzone JSON-y równolegle. Walidacja m.in.: każde KIE (`callBackUrl`, …), każdy Lyria (`model` z `lyria`), każdy Seedance na liście (`model` z `seedance`, `prompt`), ElevenLabs (`model_id`, `prompt`, `music_length_ms`), każdy WaveSpeed (`variant`, `wavespeed_json`).

Opcjonalnie w `.env`: `BENCHMARK_SECRET=...` — wtedy `POST /api/preview`, `POST /api/run` i `GET /api/model-catalog` wymagają nagłówka **`X-Benchmark-Key`** z tą samą wartością (wbudowany UI go nie wysyła; użyj np. `curl` albo wyłącz `BENCHMARK_SECRET` na lokalny podgląd w przeglądarce).

## Mapowanie pól → API

| UI | KIE | WaveSpeed MiniMax | OpenRouter Lyria | ElevenLabs Music |
|----|-----|---------------------|------------------|------------------|
| Tytuł | `title` | w `prompt` | w `messages` | w `prompt` |
| Styl | `style` | w `prompt` | w `messages` | w `prompt` |
| Słowa | `prompt` (customMode) | `lyrics` | w `messages` | w `prompt` |
| Instrumental | `instrumental` | `is_instrumental` (music-2.6) | w `messages` | w `prompt` |
| Model | wiersze **KIE — Suno** (bez wierszy — brak zadania KIE) | wiersze **WaveSpeed** (bez wierszy — brak zadania WS) | wiersze **OpenRouter — muzyka** (Lyria) | wiersze **ElevenLabs** (`music_v1`) |
| Długość (min) | dopisek w `style` | dopisek w `prompt` | w tekście promptu | `music_length_ms` (min. 30 s w benchmarku) |

## Limity odpowiedzi

Artefakty w base64 tylko gdy rozmiar surowy **≤ 10 MB** na plik — większe wideo Seedance dostajesz jako link CDN w `media_url`.

## Struktura

- `benchmark/main.py` — FastAPI + endpointy
- `benchmark/kie.py` — KIE generate / record-info / download
- `benchmark/wavespeed_minimax.py` — WaveSpeed MiniMax
- `benchmark/openrouter_media.py` — Lyria (`/chat/completions`) + Seedance (`/videos` + poll)
- `benchmark/elevenlabs_music.py` — ElevenLabs `POST /v1/music`
- `benchmark/model_catalog.py` — KIE, WaveSpeed, Lyria (max 10), Seedance (wideo), ElevenLabs
- `static/index.html` — formularz + wiersze modeli

Po zakończeniu researchu możesz usunąć cały folder `research/music-provider-benchmark` bez wpływu na główny projekt.
