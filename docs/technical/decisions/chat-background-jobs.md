# ADR: zadania w tle w procesie web service

**Data:** 2026-08-28  
**Status:** zaakceptowany

## Kontekst

Ciężkie narzędzia czatu (grafika, muzyka, PPTX) mogą przekraczać timeout HTTP. Render Background Worker kosztuje od $7/mc.

## Decyzja

- Tabela `generation_jobs` w Postgresie.
- `POST /v1/chat` → **202** `{ job_id }`; wykonanie jako zadanie w tle w **tym samym procesie** uvicorn.
- `GET /v1/jobs/{id}` — status i wynik; frontend odpytuje do `done`.

## Uzasadnienie

- Brak płatnego workera na Render Free.
- Odpytywanie statusu utrzymuje instancję wybudzoną (cold start).
- Użytkownik może zamknąć kartę i wrócić po wynik (W4).

## Konsekwencje

- Przy wielu równoległych zadaniach 512 MB RAM może być wąskim gardłem — strumieniowanie do Storage, bez buforowania całych plików.
- Osobny worker pozostaje opcją skalowania w przyszłości.

## Delta 2026-09-06 — CAS + reaper + jedna aktywna job

**ADDED**

- `claim_job_running`: `UPDATE … WHERE id = ? AND status = 'pending'` (CAS). Runner kończy pracę, jeśli claim się nie uda (już `running`/`done`/`error`).
- `conversation_has_active_chat_job`: `POST /v1/chat` zwraca **409** z istniejącym `job_id`, gdy rozmowa ma job `pending`/`running`.
- `reap_stale_running_jobs(max_age_minutes=15)`: `running` ze starym `updated_at` → `error` (polski komunikat). Wywołanie przy starcie aplikacji (lifespan) oraz przed utworzeniem nowej job.

**WHY**

- Podwójny runner albo odświeżenie karty mogło odpalić KIE/Lyria drugi raz.
- Job zostawiona w `running` po crashu procesu blokowała rozmowę bez limitu czasu.
