# Zużycie LLM per użytkownik w panelu admina — design

**Data:** 2026-08-31

## Cel

Administrator widzi w tabeli **Użytkownicy** (`/admin/users`) bieżące zużycie LLM (koszt USD i tokeny w miesiącu kalendarzowym UTC) obok skonfigurowanego limitu miesięcznego — bez przechodzenia do osobnej strony monitoringu.

## Wymagania (Given / When / Then)

- **Given** zalogowany admin z poprawnym `X-Admin-Key`
- **When** otwiera `/admin/users`
- **Then** każdy wiersz ma kolumnę „Zużycie LLM (miesiąc UTC)” z kosztem USD, liczbą tokenów oraz stosunkiem do limitu (`$zużyte / $limit`), gdy limit obowiązuje

- **Given** użytkownik bez wpisów w `llm_usage_log` w bieżącym miesiącu UTC
- **When** admin odświeża listę
- **Then** zużycie pokazuje `$0,00` i `0 tokenów`

- **Given** użytkownik z `llm_cost_month_usd >= effective_llm_monthly_cost_limit_usd` i aktywnym limitem per konto
- **When** admin przegląda listę
- **Then** wiersz jest oznaczony jako „Limit wyczerpany” (czerwony tekst)

- **Given** wpisy `dry_run=true` w `llm_usage_log`
- **When** liczone jest zużycie
- **Then** nie wchodzą do sum (jak w monitoringu i egzekwowaniu limitów)

## API

`GET /v1/admin/users` — rozszerzony model `AdminUserResponse`:

| Pole | Typ | Opis |
|------|-----|------|
| `llm_cost_month_usd` | float | Suma `cost_usd` od 1. dnia miesiąca UTC (bez dry-run) |
| `llm_tokens_month` | int | Suma `total_tokens` w tym samym okresie |
| `llm_monthly_limit_reached` | bool | `true` gdy limit efektywny istnieje i koszt ≥ limit |

Istniejące pola limitu (`effective_llm_monthly_cost_limit_usd`, `uses_site_default_llm_monthly_limit`) bez zmian semantyki.

## UI

Strona `AdminUsersPage`: nowa kolumna między rate limitem a limitem kosztu. Limit edycji pozostaje w osobnej kolumnie i akcjach.

Monitoring (`GET /v1/admin/monitoring`) — uzupełniony o `tokens_month_utc` w `per_user_llm_costs` (spójność danych).

## Decyzje

- **Źródło danych:** `llm_usage_log` (jak reszta systemu limitów).
- **Okres:** miesiąc kalendarzowy UTC — zgodnie z egzekwowaniem limitów w `assert_user_within_monthly_cost_limit`.
- **Brak nowych endpointów** — rozszerzenie istniejącego `GET /v1/admin/users` (jedno żądanie, jedna tabela).
