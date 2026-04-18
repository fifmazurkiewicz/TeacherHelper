# core/file-context — kontekst plików dla modelu

## Odpowiedzialność

1. **Indeksowanie** po zapisie/zmianie pliku: ekstrakcja tekstu (DOCX/TXT/JSON/MD), podział na fragmenty (chunking), generowanie embeddingów, zapis do PostgreSQL + Qdrant.
2. **Wyszukiwanie semantyczne** — Qdrant (cosine similarity na wektorach), filtrowanie po `user_id`.
3. **Załadowanie kontekstu** — wybór fragmentów (limit tokenów), budowa załączników do API LLM.
4. **Audyt** — log każdego odczytu treści na potrzeby AI (`ai_read_audit`).

## Zaimplementowane

- Chunking: stały rozmiar 480 znaków, overlap 80.
- Embeddingi: **OpenAI `text-embedding-3-small`** (wymiar konfigurowalny, domyślnie 1536). Fallback na deterministyczny stub (SHA-256) gdy brak klucza `OPENAI_API_KEY`.
- Batch embedding — wiele chunków indeksowanych jednym wywołaniem API.
- **Qdrant** — wyszukiwanie wektorowe (cosine distance), filtrowane po `user_id`.
- Przechowywanie embeddingów: JSONB w PostgreSQL (tabela `file_chunks`) + wektory w Qdrant.
- Ekstrakcja tekstu: TXT, MD, JSON, DOCX (python-docx + fallback XML).
- Audyt odczytu: tabela `ai_read_audit` z `user_id`, `file_asset_id`, `purpose`.

## Konfiguracja

```
OPENAI_API_KEY=sk-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=file_chunks
```

Przy zmianie dostawcy/wymiaru embeddingów należy przeindeksować pliki (endpoint `POST /v1/files/{id}/reindex`).

## Zależności zewnętrzne

- **OpenAI API** — embeddingi (`text-embedding-3-small` / `text-embedding-3-large`).
- **Qdrant** — baza wektorowa (wyszukiwanie semantyczne).
- **httpx** — klient HTTP do wywołań API.
- Biblioteki ekstrakcji: `python-docx`; w przyszłości `PyMuPDF`, `python-pptx`.

## Zasady bezpieczeństwa

- Tylko pliki należące do użytkownika (`user_id` w filtrze Qdrant + PostgreSQL).
- Inteligentny skrót treści — nie wysyłać zawsze pełnych dużych plików.
- Brak trwałego „zapamiętywania" plików po stronie dostawcy modelu.

## Do zrobienia

- Ekstrakcja tekstu z PDF, PPTX, obrazów (vision API), wideo (transkrypcja).
