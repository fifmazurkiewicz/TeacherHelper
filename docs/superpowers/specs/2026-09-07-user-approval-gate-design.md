# User approval gate — design

**Date:** 2026-09-07  
**Status:** approved (product)  
**First implementation:** TeacherHelper  
**Follow-on repos:** Langy, Medical Intelligence (PubMedResearcher), Family Organiser, Coach (goat)

## Goal

The portfolio landing page (`fmazurkiewicz.dev`) links public apps. Anyone can create an account. Paid or generative work must not run until an admin **Accepts** the user. Until then the user may log in and only sees a waiting screen. On Accept, apps that already have a monthly spend quota grant the **$10** default.

## Product contract (all five landing apps)

Applies to: Family Organiser, Coach, Teacher Helper, Medical Intelligence, Langy.

| Rule | Decision |
|---|---|
| Signup / login | Remain public (Supabase or equivalent). |
| Unapproved session | One waiting screen. No product chrome (no chat, materials, admin nav). Logout works. |
| Admin action | Accept / Revoke **toggle** (`is_approved`). No separate rejected state. Revoked users see the same waiting screen. |
| Existing accounts | Grandfathered: migration sets `is_approved = true` on all current rows. |
| Admin allowlist | Emails in that app’s `ADMIN_EMAILS` (or equivalent) are auto-approved on first profile create. |
| $10 grant | On Accept, only where the app already has a spend quota. TeacherHelper: site default `DEFAULT_USER_LLM_MONTHLY_COST_LIMIT_USD` ($10/month UTC) via `llm_monthly_cost_limit_usd = NULL`. Langy: existing `spend_cap_usd` default 10. Coach: existing usage budget. Family Organiser: gate only — do not invent a $10 quota. |
| Re-accept | Do not overwrite a custom quota the admin already set. |
| Enforcement | Backend 403 plus waiting page. Frontend-only lock is insufficient. |
| Notifications | None in v1. Admin checks the users list. |

Each follow-on app gets its own spec/plan in its repo, copying this contract. This document is the TeacherHelper implementation spec plus the shared rules.

## TeacherHelper — data

- Column `users.is_approved`: `BOOLEAN NOT NULL`, default `false`.
- Migration: add column, then `UPDATE users SET is_approved = true` for all existing rows, then set server default `false` for inserts.
- `_ensure_user_profile` (first authenticated request):
  - New row: `is_approved = false`, unless normalized email is in `ADMIN_EMAILS` → `true`.
  - Existing row: do not change `is_approved` (role policy for `ADMIN_EMAILS` still applies). Revoke sticks until an admin Accepts again.
- Accept: `is_approved = true`. Leave `llm_monthly_cost_limit_usd` unchanged (`NULL` → $10 site default).
- Revoke: `is_approved = false` only. Do not change the cost limit.
- Legacy `POST /v1/auth/register` (only when Supabase is off): new users `is_approved = false` unless `ADMIN_EMAILS`.

## TeacherHelper — API and gate

### Allowed without approval

- `GET /api/health`, `GET /api/health/ready`
- KIE music webhook (no JWT)
- `GET /v1/auth/me` (returns `is_approved`)
- Login / register (unauthenticated)

### Blocked without approval

Every other authenticated `/v1/*` route, including chat, conversations, projects, topics, files, jobs, voice, sound, music, intent, and `/v1/admin/*`.

Response: **403** with

```json
{ "detail": { "code": "account_pending_approval", "message": "Konto oczekuje na akceptację administratora." } }
```

Not 401 — the session is valid.

### Dependencies

- `get_current_user` — identity + profile create (unchanged, plus `is_approved` on insert).
- `require_approved` — 403 if `not user.is_approved`.
- `ApprovedUser` — `CurrentUser` + `require_approved`. Use on all feature routes that today take `CurrentUser`, except `/v1/auth/me`.
- `require_admin` — still requires `role == admin`, and also requires approved.

### Admin

- `GET /v1/admin/users` / `AdminUserResponse`: add `is_approved`.
- `PATCH /v1/admin/users/{id}`: optional `is_approved` (Accept / Revoke).
- An admin cannot set `is_approved = false` on **themselves** (403).

### `GET /v1/auth/me`

`UserResponse` adds `is_approved: bool`.

## TeacherHelper — UI

Polish copy (existing product language).

**Waiting screen** (`ProtectedLayout` after a valid session):

- Load `GET /v1/auth/me`. If `is_approved === false`: no `Nav`, no assistant / materials / admin outlet.
- Title: **Konto oczekuje na akceptację**
- Body: an admin must accept the account before the assistant can be used.
- Actions: **Sprawdź status** (re-fetch `/me`), **Wyloguj**
- Poll `/me` every 15 seconds. When `is_approved` becomes true, render the normal app without a full page reload requirement.
- If a feature call returns `account_pending_approval`, show this same screen (stale client after Revoke).

**Admin `/admin/users`:**

- Column **Status**: Oczekuje / Zaakceptowany. Pending rows visually distinct (badge).
- **Akceptuj** / **Cofnij dostęp** → `PATCH` with `is_approved`.
- Hide **Cofnij dostęp** on the signed-in admin’s own row.

## Error handling

| Case | Behaviour |
|---|---|
| Unapproved feature API | 403 `account_pending_approval` |
| Admin revokes self | 403, no state change |
| Missing profile email on first JWT | 401 (existing) — cannot create profile |
| Health / webhook | Unchanged, no approval check |

## Testing (Given / When / Then)

- **Given** a new user whose email is not in `ADMIN_EMAILS`  
  **When** they authenticate and the profile is created  
  **Then** `is_approved` is false; `GET /v1/auth/me` is 200; `POST /v1/chat` is 403 `account_pending_approval`

- **Given** that pending user  
  **When** an admin PATCHes `is_approved: true`  
  **Then** `/me` reports approved; chat is allowed; effective monthly LLM limit is the site default ($10) when `llm_monthly_cost_limit_usd` is NULL

- **Given** an approved user  
  **When** an admin PATCHes `is_approved: false`  
  **Then** feature routes 403 and the SPA shows the waiting screen

- **Given** first login with an `ADMIN_EMAILS` address  
  **When** the profile is created  
  **Then** `is_approved` is true without a manual Accept

- **Given** rows that existed before the migration  
  **When** the migration runs  
  **Then** those users are `is_approved = true`

- **Given** an admin viewing their own row  
  **When** they attempt to revoke themselves  
  **Then** 403 and they remain approved

- **Given** an unapproved session in the SPA  
  **When** they open any protected route  
  **Then** they see the waiting screen, not the assistant

## Out of scope (TeacherHelper v1)

- Email/Slack notify on new signup
- Separate “rejected” copy
- Changing `DEFAULT_USER_LLM_MONTHLY_COST_LIMIT_USD`
- Implementing Langy / Medical Intelligence / Family Organiser / Coach in this repo

## Decisions

| Date | Decision | Why |
|---|---|---|
| 2026-09-07 | Waiting screen only (not a disabled chrome) | Clear; nothing to poke at |
| 2026-09-07 | Grandfather existing users | Avoid locking current teachers on deploy |
| 2026-09-07 | Accept/Revoke boolean, one waiting screen | YAGNI vs pending/rejected/approved enum |
| 2026-09-07 | `ADMIN_EMAILS` skip the queue | Admin UI is behind the waiting screen |
| 2026-09-07 | `is_approved` column, not reuse of cost-limit NULL | Access ≠ billing; NULL already means $10 default |
| 2026-09-07 | $10 = existing site default on Accept | No second quota system |
| 2026-09-07 | All five landing apps get the gate; $10 only where a quota already exists | Public hub; Family Organiser has no LLM cap |
| 2026-09-07 | TeacherHelper first; other repos copy this contract | Separate auth stacks |
