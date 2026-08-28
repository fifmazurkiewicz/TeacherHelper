# ADR: Supabase Auth zamiast własnego JWT

**Data:** 2026-08-28  
**Status:** zaakceptowany

## Kontekst

Auth opierał się na własnym JWT (bcrypt + python-jose), endpointach `register`/`login` i tokenie `th_access_token` w localStorage.

## Decyzja

- **Frontend:** `@supabase/supabase-js` — `signUp`, `signInWithPassword`, `signInWithOAuth('google')`.
- **Backend:** weryfikacja JWT przez JWKS Supabase (PyJWT + cache kluczy), **bez** `supabase-py`.
- Tabela `users` = profil aplikacyjny (`id` = UUID z Supabase Auth); tworzony przy pierwszym uwierzytelnionym żądaniu.

## Uzasadnienie

- Zgodność ze standardem deploy (`deployment-standard.mdc`).
- Google OAuth bez własnej implementacji OAuth flow.
- Baza od zera — brak migracji haseł użytkowników.

## Konsekwencje

- Usuwamy: `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRE_HOURS`, endpointy `register`/`login`.
- Seed admina (`007`) wyłączony na produkcji: `SKIP_ADMIN_SEED=1`.
- Nowe zmienne: `SUPABASE_URL`, `SUPABASE_JWKS_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`.
