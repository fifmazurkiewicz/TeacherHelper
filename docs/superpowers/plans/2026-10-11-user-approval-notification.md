# TeacherHelper Approval Notification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send one administrator email when a new non-admin account enters TeacherHelper's existing approval queue.

**Architecture:** The first user-resolution insert records and sends once through an async backend adapter; existing admin UI retries failures.

**Tech Stack:** Existing FastAPI backend, React frontend, Supabase/Postgres, installed `httpx`, Resend HTTP API.

**Spec:** docs/superpowers/specs/2026-10-11-user-approval-notification-design.md

## Global Constraints

- Backend-only `RESEND_API_KEY`, `RESEND_MAIL=fifmazurkiewicz@gmail.com`, and `RESEND_FROM=Powiadomienia <powiadomienia@fmazurkiewicz.dev>`.
- Reuse installed `httpx`; no Resend SDK and no shared service.
- A delivery failure never blocks account creation, login, the waiting screen, or the existing 403 gate.
- Preserve the existing monthly USD limit; do not add a token quota.


## Review Focus

- A repeated login/account read must not email twice.
- Auto-approved admin accounts and migrated existing accounts must be silent.
- Failure must leave access pending and allow an admin retry.
- A normal user must not access retry or provider data.
- The pending contact link must not expose app navigation.

---

### Task 1: Persist per-account notification state

**Files:**
- Create: `backend/migrations/versions/017_user_approval_notification.py`
- Modify: `backend/teacher_helper/infrastructure/db/models.py`
- Modify: `backend/teacher_helper/config.py`
- Modify: `.env.example`
- Test: `backend/tests/test_user_approval.py`

**Interfaces:**
- Account fields: `approval_notification_status`, `approval_notification_sent_at`, `approval_notification_error`.
- Settings: `resend_api_key`, `resend_mail`, `resend_from`.

- [ ] **Step 1: Write the failing persistence test**

```python
assert user.approval_notification_status == "pending"
assert user.approval_notification_sent_at is None
```

- [ ] **Step 2: Run it**

Run: `cd backend && pytest tests/test_user_approval.py -q`

Expected: FAIL because the fields do not exist.

- [ ] **Step 3: Add migration, model fields, and settings**

Add a status, timestamp, and bounded error column. Existing rows receive `sent` so no historical email is emitted; only a newly inserted non-admin receives `pending`. Add documented examples for all three Resend variables.

- [ ] **Step 4: Verify and commit**

Run: `cd backend && pytest tests/test_user_approval.py -q`

Expected: PASS.

```bash
git add backend/migrations/versions/017_user_approval_notification.py backend/teacher_helper/infrastructure/db/models.py backend/teacher_helper/config.py .env.example backend/tests/test_user_approval.py
git commit -m "feat: store TeacherHelper approval notification state"
```

### Task 2: Send one non-blocking email

**Files:**
- Create: `backend/app/infrastructure/resend_mail.py`
- Modify: `backend/teacher_helper/adapters/http/deps.py`
- Test: `backend/tests/test_user_approval.py`

**Interfaces:**
- `send_approval_notification(account_email: str | None, admin_url: str) -> None`.
- State transition is `pending → sent` or `pending → failed`.

- [ ] **Step 1: Write failing delivery tests**

```python
assert first.approval_notification_status == "sent"
assert second_login_email_calls == 0
assert failed_user.is_approved is False
```

- [ ] **Step 2: Run them**

Run: `cd backend && pytest tests/test_user_approval.py -q`

Expected: FAIL because the adapter does not exist.

- [ ] **Step 3: Implement minimum delivery**

Use a five-second `httpx` POST to `https://api.resend.com/emails` after the account record is durable. Send only app name, account email, creation time, current USD limit, and admin URL. Store a safe bounded failure string without logging headers or keys.

- [ ] **Step 4: Verify and commit**

Run: `cd backend && pytest tests/test_user_approval.py -q`

Expected: PASS.

```bash
git add backend/app/infrastructure/resend_mail.py backend/teacher_helper/adapters/http/deps.py backend/tests/test_user_approval.py
git commit -m "feat: notify TeacherHelper admin about pending accounts"
```

### Task 3: Add admin retry, status, and contact fallback

**Files:**
- Modify: `backend/teacher_helper/adapters/http/routes_admin.py`
- Modify: `frontend/src/pages/AdminUsersPage.tsx`
- Modify: `frontend/src/pages/PendingApprovalPage.tsx`
- Test: `backend/tests/test_user_approval.py`

**Interfaces:**
- Admin-only `POST /admin/users/{user_id}/approval-notification` (use the repository's existing API prefix).
- Existing users-list DTO gains delivery status and sent time.

- [ ] **Step 1: Write failing authorization and UI tests**

```python
assert retry_as_non_admin.status_code == 403
```

```tsx
expect(screen.getByRole("link", { name: /napisz do administratora/i }))
  .toHaveAttribute("href", expect.stringContaining("mailto:fifmazurkiewicz@gmail.com"));
```

- [ ] **Step 2: Run them**

Run: `cd backend && pytest tests/test_user_approval.py -q`

Expected: FAIL because retry/status/contact UI is absent.

- [ ] **Step 3: Implement the guarded surface**

Return state in the existing admin list. Only the existing approved-admin dependency may retry a `pending` or `failed` delivery; refresh the row after completion. Render it beside the existing USD limit and approval control. Add one accessible mailto link on the waiting screen only.

- [ ] **Step 4: Verify and commit**

Run: `cd backend && pytest tests/test_user_approval.py -q && cd ../frontend && npm test && npm run lint && npm run build`

Expected: PASS.

```bash
git add backend/teacher_helper/adapters/http/routes_admin.py frontend/src/pages/AdminUsersPage.tsx frontend/src/pages/PendingApprovalPage.tsx backend/tests/test_user_approval.py
git commit -m "feat: manage TeacherHelper approval notifications"
```

### Task 4: Roll out safely

**Files:**
- Modify: `docs/technical/configuration.md`

- [ ] **Step 1: Document and perform the smoke test**

Document Resend domain verification and required deployment secrets. Create one non-admin test account, verify exactly one mail, set the existing USD cap, approve it, and verify the feature gate opens.

- [ ] **Step 2: Commit**

```bash
git add docs/technical/configuration.md
git commit -m "docs: add TeacherHelper approval notification rollout"
```

