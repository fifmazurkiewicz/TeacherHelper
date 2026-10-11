# TeacherHelper — approval notification design

## Goal

Notify `fifmazurkiewicz@gmail.com` once when a newly created, non-admin TeacherHelper account enters the existing approval queue. The administrator can set the existing monthly USD cost limit and accept the account from the existing admin page.

## Scope and configuration

- This design is TeacherHelper-only; it does not call another application or shared notification service.
- Add backend-only `RESEND_API_KEY`, `RESEND_MAIL=fifmazurkiewicz@gmail.com`, and `RESEND_FROM=Powiadomienia <powiadomienia@fmazurkiewicz.dev>` settings. The Resend key is a TeacherHelper-specific sending-only key.
- Retain `ADMIN_EMAILS=fifmazurkiewicz@gmail.com`. The allowlisted admin remains auto-approved on first profile creation.

## Flow

The existing user resolution and first-profile creation boundary creates a non-admin `UserORM(is_approved=false)`. On that insert, it records one pending approval notification and sends one transactional email through Resend. Later logins must not create another notification. The mail contains only the application name, new account email, creation time, current default monthly USD limit, and the existing admin-users URL.

Resend failure never blocks login, profile creation, the waiting screen, or the 403 feature gate. Store `pending`, `sent`, or `failed`, a sent timestamp, and a safe error summary. The admin users response exposes that status. The existing admin users page adds a retry action for `failed` or unsent notifications; retry is admin-only and updates the same record. No automatic retry is added.

The existing pending-approval page adds an accessible `mailto:fifmazurkiewicz@gmail.com` link with an app-specific subject. It does not expose feature navigation.

## Data, security, and UI

- Add notification state to the local user record through an Alembic migration, never storing the Resend key, message body, or raw provider response.
- Do not send for admin/allowlisted accounts, approved accounts, or previously-notified accounts.
- Keep the Resend call in a small backend adapter with an injectable transport for tests; never import it in the frontend or commit a key.
- Reuse `llm_monthly_cost_limit_usd` and the existing approval action. No token-count limit is introduced.

## Tests and rollout

Test new non-admin creation sends exactly one mail; a later login sends none; a provider error leaves the account pending and records `failed`; an admin retry sends once; non-admin retry is forbidden; and the pending page contains the contact link. Configure the three environment variables in TeacherHelper deployment before enabling the release, then create a test account and confirm one mail and manual acceptance.
