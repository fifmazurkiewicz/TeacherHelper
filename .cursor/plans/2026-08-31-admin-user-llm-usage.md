# Plan: kolumna zużycia LLM w panelu admina

**Data:** 2026-08-31  
**Spec:** `docs/superpowers/specs/2026-08-31-admin-user-llm-usage-column-design.md`

## Decyzje

- Zużycie w `GET /v1/admin/users`, nie osobny endpoint.
- Koszt + tokeny miesiąca UTC; dry-run wykluczony.
- UI: kolumna „Zużycie LLM (miesiąc UTC)” + oznaczenie wyczerpania limitu.

## Zadania

- [x] `llm_usage_month_by_user_id`, `user_llm_usage_month` w `usage_limits.py`
- [x] Pola usage w `AdminUserResponse` + `list_users`
- [x] Kolumna w `AdminUsersPage.tsx`
- [x] Dokumentacja `admin-panel.md`
- [x] Test logiki `llm_monthly_limit_reached`
