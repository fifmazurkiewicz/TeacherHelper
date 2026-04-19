# Image provider benchmark (research)

Samodzielny mini-projekt w tym samym duchu co `research/music-provider-benchmark`: **jedno wejście (prompt)** → równoległe wywołania (**OpenAI Images** / **DALL·E**, **Stability Stable Image** v2beta, **OpenRouter** z `modalities` dla modeli z wyjściem obrazu) → odpowiedź JSON z **`trace`** oraz **`artifacts`** (obrazy w base64, do ok. 10 MB surowego pliku na artefakt).

Nie jest częścią backendu TeacherHelper.

## Wymagania

- Python 3.11+
- Klucze API (wg używanych wierszy): `OPENAI_API_KEY`, `STABILITY_API_KEY`, `OPENROUTER_API_KEY`

## Uruchomienie

```bash
cd research/image-provider-benchmark
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy .env.example .env
# uzupełnij .env
uvicorn benchmark.main:app --host 127.0.0.1 --port 8766
```

W przeglądarce: **http://127.0.0.1:8766/** (inny port niż benchmark muzyki, żeby nie kolidowały).

## Dwuetapowy flow

1. **`GET /api/model-catalog`** — listy: modele OpenAI (DALL·E), usługi Stability (`core` / `ultra` / `sd3`), modele OpenRouter z `output_modalities=image` (przy braku klucza — fallback).
2. **`POST /api/preview`** — z formularza + **wierszy „Dodaj model”** buduje **`openai_jsons`**, **`stability_jobs`**, **`openrouter_image_jsons`**. Bez wywołań do zewnętrznych API.
3. W UI edytujesz JSON przed uruchomieniem.
4. **`POST /api/run`** — wysyła zatwierdzone payloady równolegle.

Opcjonalnie `BENCHMARK_SECRET` — wtedy `X-Benchmark-Key` na `preview` / `run` / `model-catalog` (statyczny UI go nie wysyła).

## Struktura

- `benchmark/main.py` — FastAPI
- `benchmark/openai_images.py` — `POST /v1/images/generations`
- `benchmark/stability_images.py` — multipart `stable-image/generate/{service}`
- `benchmark/openrouter_images.py` — `chat/completions` + obrazy w `message.images`
- `benchmark/model_catalog.py` — katalogi i pobieranie modeli OpenRouter
- `static/index.html` — formularz

## Uwagi

- **DALL·E 2** ma inny zestaw rozmiarów niż DALL·E 3 — przy błędzie rozmiaru sprawdź [dokumentację OpenAI](https://platform.openai.com/docs/guides/images).
- **Stability `sd3`**: jeśli endpoint na koncie zwraca 404, usuń wiersz `sd3` i zostań przy `core` / `ultra` (zależnie od dostępności na platformie).
- **Budżet**: stawki zmieniają się często — przed szacowaniem kosztów zweryfikuj bieżący cennik u wybranego dostawcy.
