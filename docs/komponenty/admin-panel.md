# admin/panel — administracja

## Zakres

- Dashboard: użytkownicy, treści, zużycie API, storage, koszty, alerty.
- Konta: CRUD, role, podgląd aktywności i plików, resetowanie haseł.
- Konfiguracja: limity per użytkownik (rate_limit_rpm), modele AI.
- Monitoring: LLM usage, incydenty systemowe, webhook alerty.

## Zaimplementowane

- `GET /v1/admin/users` — lista użytkowników (status `is_approved`, rola, rate limit, **zużycie LLM miesiąc UTC**: koszt USD, tokeny, flaga wyczerpania limitu**, limit kosztu LLM).
- `PATCH /v1/admin/users/{id}` — zmiana roli, rate limit, limit kosztu LLM, **Accept/Revoke** (`is_approved`). Admin nie może cofnąć dostępu własnego konta.
- `DELETE /v1/admin/users/{id}/rate-limit` — reset indywidualnego limitu RPM.
- `DELETE /v1/admin/users/{id}/llm-monthly-cost-limit` — przywrócenie domyślnego limitu kosztu (`DEFAULT_USER_LLM_MONTHLY_COST_LIMIT_USD`).
- `POST /v1/admin/users/{id}/reset-password` — resetowanie hasła.
- `GET /v1/admin/stats` — statystyki (użytkownicy, pliki, audyty).
- `GET /v1/admin/monitoring` — pełny monitoring (LLM, koszt per user, incydenty, alerty).
- `POST /v1/admin/alerts/test-webhook` — test webhooka.

### Zużycie LLM per użytkownik (lista użytkowników)

Pola w odpowiedzi `GET /v1/admin/users`:

| Pole | Znaczenie |
|------|-----------|
| `is_approved` | Accept/Revoke: `false` = waiting screen; `true` = pełny dostęp |
| `llm_cost_month_usd` | Koszt USD od 1. dnia miesiąca UTC (`llm_usage_log`, bez dry-run) |
| `llm_tokens_month` | Suma tokenów w tym samym okresie |
| `llm_monthly_limit_reached` | `true` gdy `llm_cost_month_usd >= effective_llm_monthly_cost_limit_usd` |
| `effective_llm_monthly_cost_limit_usd` | Limit obowiązujący (własny, domyślny z env lub brak przy `0` w bazie) |

Frontend: `/admin/users` — kolumna **Zużycie LLM (miesiąc UTC)** (`$zużyte / $limit`, tokeny, etykieta przy wyczerpaniu).

Szczegóły limitów: `DEFAULT_USER_LLM_MONTHLY_COST_LIMIT_USD`, `LLM_MONTHLY_COST_SOFT_LIMIT_USD`, `LLM_MONTHLY_COST_HARD_LIMIT_USD` w `docs/technical/configuration.md`.

## Zależności

**PostgreSQL**, **Redis**; dostęp tylko dla roli administrator (i audytowany).
