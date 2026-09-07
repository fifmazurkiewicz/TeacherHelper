# User approval gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** New TeacherHelper signups wait on a single pending screen until an admin Accepts them; Accept leaves the existing $10/month UTC LLM default in place.

**Architecture:** Boolean `users.is_approved` (grandfather existing rows). `get_current_user` still creates the profile. `require_approved` 403s feature routes with `account_pending_approval`. `/v1/auth/me` stays allowed. SPA `ProtectedLayout` shows the waiting screen. Admin PATCH toggles the flag.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, React/Vite, existing admin users table.

**Spec:** `docs/superpowers/specs/2026-09-07-user-approval-gate-design.md`

## Global Constraints

- Waiting screen only; no product chrome until approved.
- `ADMIN_EMAILS` auto-approved on **insert only**; revoke sticks.
- Accept does not overwrite `llm_monthly_cost_limit_usd` (NULL = $10 site default).
- Admin cannot revoke themselves.
- Polish UI copy. Health and KIE webhook stay ungated.
- Isolate in `_harden/TeacherHelper-approval`; do not edit dirty main WIP.
- Follow-on apps (Langy, Medical Intelligence, Family Organiser, Coach) copy this contract in their own repos — $10 only where a spend quota already exists.

---

### Task 1: Model + migration + create-time approval helper

**Files:**
- Create: `backend/migrations/versions/014_user_is_approved.py`
- Modify: `backend/teacher_helper/infrastructure/db/models.py`
- Modify: `backend/teacher_helper/adapters/http/deps.py`
- Test: `backend/tests/test_user_approval.py`

**Interfaces:**
- Produces: `UserORM.is_approved: bool`; `initial_is_approved_for_email(email: str) -> bool`

- [ ] **Step 1: Write failing tests** in `backend/tests/test_user_approval.py` for `initial_is_approved_for_email` (allowlist vs teacher) and `UserORM.is_approved` default False.
- [ ] **Step 2: Run** `cd backend && poetry run pytest tests/test_user_approval.py -v` — expect FAIL (helper/column missing).
- [ ] **Step 3: Add column + helper + migration 014** (`add_column` nullable → `UPDATE … true` → `nullable=False` server_default false).
- [ ] **Step 4: Re-run tests** — PASS.
- [ ] **Step 5: Commit** `feat(auth): add users.is_approved and allowlist insert rule`

### Task 2: `require_approved` + profile insert

**Files:**
- Modify: `backend/teacher_helper/adapters/http/deps.py`
- Modify: `backend/teacher_helper/adapters/http/routes_auth.py` (legacy register)
- Test: `backend/tests/test_user_approval.py`

**Interfaces:**
- Produces: `require_approved(user) -> UserORM`; `ApprovedUser`; 403 detail `{code, message}`

- [ ] **Step 1: Failing tests** — unapproved raises 403 `account_pending_approval`; approved returns user; `_ensure_user_profile` new teacher `is_approved=False`, admin email `True`.
- [ ] **Step 2: pytest** — FAIL.
- [ ] **Step 3: Implement `require_approved`, `ApprovedUser`, set flag on insert (and legacy register).** Do not change `is_approved` on existing rows.
- [ ] **Step 4: pytest** — PASS.
- [ ] **Step 5: Commit** `feat(auth): gate unapproved users with 403 account_pending_approval`

### Task 3: Swap feature routes + `/me` + admin PATCH

**Files:**
- Modify: all `routes_*.py` that use `CurrentUser` except `routes_auth.me`
- Modify: `backend/teacher_helper/adapters/http/schemas.py` (`UserResponse.is_approved`)
- Modify: `backend/teacher_helper/adapters/http/routes_admin.py`
- Test: `backend/tests/test_user_approval.py`, `backend/tests/test_admin_user_usage.py`

**Interfaces:**
- `UpdateUserRequest.is_approved: bool | None`
- `AdminUserResponse.is_approved: bool`
- Self-revoke → 403

- [ ] **Step 1: Failing tests** for admin response field, PATCH accept, self-revoke forbidden, `_admin_user_response` includes `is_approved`.
- [ ] **Step 2: pytest** — FAIL.
- [ ] **Step 3: Wire `ApprovedUser`, PATCH, `/me` field.** `require_admin` also requires approved.
- [ ] **Step 4: pytest** — PASS.
- [ ] **Step 5: Commit** `feat(admin): accept and revoke users via is_approved`

### Task 4: Waiting screen + admin UI

**Files:**
- Create: `frontend/src/pages/PendingApprovalPage.tsx`
- Modify: `frontend/src/components/ProtectedLayout.tsx`
- Modify: `frontend/src/pages/AdminUsersPage.tsx`
- Modify: `frontend/src/pages/ProfilePage.tsx` (Me type)
- Modify: `frontend/src/components/Nav.tsx` if it types `/me`

**Dials:** VARIANCE 3 / MOTION 2 / DENSITY 5. Preserve paper/ink/accent tokens. Polish copy from spec.

- [ ] **Step 1: Waiting page + layout fetch `/v1/auth/me`, 15s poll, logout, status button.** On `account_pending_approval` from feature calls, same screen.
- [ ] **Step 2: Admin Status column, pending first, Akceptuj / Cofnij dostęp, hide revoke on own row.** Need current user id from `/me`.
- [ ] **Step 3:** `cd frontend && npm run lint && npm run build`
- [ ] **Step 4: Commit** `feat(frontend): pending-approval screen and admin accept toggle`

### Task 5: Docs delta + verify

- [ ] Move admin/core-auth “Spec” bullets to **Zaimplementowane** after code lands.
- [ ] `cd backend && poetry run ruff check . && poetry run pytest`
- [ ] `cd frontend && npm run lint && npm run build`
