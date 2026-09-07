# ADR: Admin approval gate for new users

**Date:** 2026-09-07  
**Status:** accepted

## Context

TeacherHelper (and the other apps on `fmazurkiewicz.dev`) is publicly linked from the portfolio landing page. Supabase signup is open. The product is still a free tool for invited people only (`docs/ZASADY_I_WYMAGANIA.md`). Today the first API call creates a profile and immediately applies the $10/month LLM default.

## Decision

- Add `users.is_approved` (boolean). New profiles start unapproved unless the email is in `ADMIN_EMAILS`. Existing rows are grandfathered approved.
- Unapproved users may log in. Feature APIs return 403 `account_pending_approval`. The SPA shows a single waiting screen.
- Admin Accept/Revoke is `PATCH /v1/admin/users/{id}` with `is_approved`. Accept does not overwrite a custom `llm_monthly_cost_limit_usd`; `NULL` still means the site default $10/month UTC.
- Do not encode access in the cost-limit column (NULL already means “use site default”).

## Consequences

- Public registration stays; spend starts only after Accept.
- Follow-on: same product contract in Langy, Medical Intelligence, Family Organiser, and Coach — each in its own repo. $10 grant only where that app already has a spend quota.
- 2026-09-07: the chat unique-index migration is Alembic **015**. A second file also used revision **014**, which made Render `alembic upgrade head` fail.

Full spec: `docs/superpowers/specs/2026-09-07-user-approval-gate-design.md`.
