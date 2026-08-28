# ADR: Supabase Storage zamiast dysku lokalnego

**Data:** 2026-08-28  
**Status:** zaakceptowany

## Kontekst

Pliki użytkowników były zapisywane na dysku (`LocalStorage` → `data/storage`). Render Free nie ma trwałego dysku.

## Decyzja

Produkcja używa **Supabase Storage** przez adapter `SupabaseStorage`. Lokalnie: `STORAGE_BACKEND=local`. Pobieranie przez **signed URL**, zapis strumieniowy.

## Uzasadnienie

- Render Free traci pliki po restarcie instancji.
- Supabase Storage jest w tym samym ekosystemie co Postgres i Auth.
- Bez limitów per użytkownik i retencji na start — monitoring w dashboardzie Supabase.

## Konsekwencje

- Nowe zmienne: `SUPABASE_STORAGE_BUCKET`, `STORAGE_BACKEND`, `SUPABASE_SERVICE_ROLE_KEY` (backend).
- `STORAGE_ROOT` zostaje tylko dla trybu `local`.
