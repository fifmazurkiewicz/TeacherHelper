# ADR: pgvector zamiast Qdrant

**Data:** 2026-08-28  
**Status:** zaakceptowany

## Kontekst

Embeddingi były już przechowywane w Postgresie (`file_chunks.embedding` jako JSONB) i równolegle indeksowane w Qdrant Cloud.

## Decyzja

Wyszukiwanie wektorowe przenosimy w całości do **pgvector** w Supabase Postgres. Kolumna `embedding` → `vector(1536)` z indeksem HNSW. Moduł `infrastructure/qdrant.py` zostaje usunięty.

## Uzasadnienie

- Jeden dostawca mniej (brak Qdrant Cloud i osobnego klucza API).
- Embeddingi i metadane w jednej bazie — prostsze zapytania z filtrem `user_id` / `topic_id` w SQL.
- Sygnatura `semantic_search_chunks(...)` bez zmian — warstwa use case nietknięta.

## Konsekwencje

- Wymaga rozszerzenia `vector` w Postgresie (Supabase ma pgvector wbudowany).
- Usuwamy: `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`, zależność `qdrant-client`.
