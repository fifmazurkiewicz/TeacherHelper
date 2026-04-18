# admin/panel — administracja

## Zakres

- Dashboard: użytkownicy, treści, zużycie API, storage, koszty, alerty.
- Konta: CRUD, role, podgląd aktywności i plików, resetowanie haseł.
- Konfiguracja: limity per użytkownik (rate_limit_rpm), modele AI.
- Monitoring: LLM usage, incydenty systemowe, webhook alerty.

## Zaimplementowane

- `GET /v1/admin/users` — lista użytkowników.
- `PATCH /v1/admin/users/{id}` — zmiana roli, rate limit.
- `DELETE /v1/admin/users/{id}/rate-limit` — reset indywidualnego limitu.
- `POST /v1/admin/users/{id}/reset-password` — resetowanie hasła.
- `GET /v1/admin/stats` — statystyki (użytkownicy, pliki, audyty).
- `GET /v1/admin/monitoring` — pełny monitoring (LLM, incydenty, alerty).
- `POST /v1/admin/alerts/test-webhook` — test webhooka.

## Zależności

**PostgreSQL**, **Redis**; dostęp tylko dla roli administrator (i audytowany).
