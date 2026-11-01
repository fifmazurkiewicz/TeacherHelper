# Sentry — TeacherHelper

## Scope and state

The owner approved SDK implementation on 2026-11-01 after service setup. Organization: `fmazurkiewicz`; data region: EU. Existing Sentry projects: `teacherhelper-web`, `teacherhelper-api`. The owner supplies deployment variables manually. This change prepares SDK code, tests and documentation; production ingestion is a separate gate.

Entrypoints: backend/teacher_helper/main.py; existing terminal exception logging in use_cases/chat_job_runner.py.

## Task list

| ID | Description | Acceptance |
| --- | --- | --- |
| SENTRY-01 | Connect official SDKs at the real process/client entrypoints, with explicit activation and the correct per-component project. | Missing/invalid DSN or an enable flag other than `true` sends no events; startup and product behavior remain usable. |
| SENTRY-02 | Report unhandled errors and caught terminal workflow failures once through existing exception boundaries or an injected edge-owned reporter. | Original responses, jobs, cancellation, access control, retries and budgets retain their behavior; no duplicate exception report. |
| SENTRY-03 | Apply the technical metadata allowlist before delivery and disable non-error products. | Actual SDK envelopes exclude private fields and attachments, including nested payloads and exception messages; known cancellations/denials do not report as failures. |
| SENTRY-04 | Prepare deployment configuration and private frontend source-map uploads where relevant. | Example variables and this runbook agree; build-time auth token is never public; public artifacts contain no source maps. |
| SENTRY-05 | Verify, review and publish source to main (ModelFabric stays local). | Existing checks plus transport/privacy tests pass; deliberate privacy break fails; independent review is resolved and CI status is recorded. |
| SENTRY-06 | Owner configures the target environment, rebuilds/redeploys and verifies a synthetic staging error per runtime. | Correct project, environment, release and useful stack locations are observed in Sentry, with no private data. This gate remains open until actual hosted/device evidence exists. |

Execution status and evidence: [progress](../../.agent/context/changes/sentry-error-monitoring/progress.md), [plan](../../.agent/context/changes/sentry-error-monitoring/plan.md), [evidence](../../.agent/context/changes/sentry-error-monitoring/evidence.md).

## Data contract

Never transmit uploaded teaching materials, student information, RAG snippets, prompts and generated media. Only component, known environment, commit SHA, exception category, sanitized application-code stack positions and validated technical Debug IDs may leave. Rebuild events from an allowlist rather than deleting only obvious secrets. Drop raw messages, user/request/response/context/extra/breadcrumb data, local variables and attachments. Default integrations are disabled and only necessary error handlers are selected. No tracing, profiling, Session Replay, full log streaming, metrics or AI instrumentation. Organization-level scrubbers are a backstop, not proof that data never left the app.

Monitoring initialization/transport failure must not change application results. Normal authorization/validation denials, cancellations and spend limits are not application failures. Do not add public debug routes or send real user data for verification.

## Manual environment setup

DSNs come from Sentry → Settings → Projects → the exact project → Client Keys (DSN). A DSN selects the Sentry project independently of the Render/Vercel account. Example files contain names and empty values only. Keep all enable flags `false` until verification is accepted, then set `true` in the selected environment.

### Render — backend

Service → Environment → add the following values. Save only while preparing; deploy after the matching source is available. Add them separately to an independently deployed worker that uses the same API code.

| Variable | Value |
| --- | --- |
| `SENTRY_ENABLED` | `true` when activating; otherwise `false` |
| `SENTRY_DSN` | DSN for `teacherhelper-api` |
| `SENTRY_ENVIRONMENT` | `production`, `staging`, `preview`, `development` or `test` |
| `SENTRY_RELEASE` | Optional 7–40 character git SHA; falls back to `RENDER_GIT_COMMIT` |

The Python adapter reads process environment. For local opt-in, export these names in the process environment; do not assume a Pydantic `.env` loader exports them globally.

### Vercel — Vite/React

Project → Settings → Environment Variables:

| Variable | Value |
| --- | --- |
| `VITE_SENTRY_ENABLED` | `true` when activating |
| `VITE_SENTRY_DSN` | DSN for `teacherhelper-web` |
| `VITE_SENTRY_ENVIRONMENT` | `production`, `preview` or `staging` as appropriate |
| `VITE_SENTRY_RELEASE` | Optional matching build commit SHA |
| `SENTRY_ORG` | `fmazurkiewicz` |
| `SENTRY_PROJECT` | `teacherhelper-web` |
| `SENTRY_AUTH_TOKEN` | Build-only Sentry CI token, never prefixed with `VITE_` |

The build creates hidden maps only when the upload token is supplied and deletes maps after upload. Without it no public maps are generated. Validated Debug IDs retain stack association even when no release is configured. Rebuild after changing browser configuration.

## Activation, verification and rollback

1. Complete local checks and independent review; inspect the actual emitted test envelope using a fake transport. A deliberately disabled privacy filter must make the test fail.
2. Owner sets the exact project DSNs, enable flags and environment names in the appropriate service/build environment. No token is pasted into chat or committed.
3. Rebuild/redeploy. Use a synthetic exception in a non-production test path, not a permanent public error endpoint and not real user content. Verify correct project/environment and useful code locations; verify private map resolution when maps are configured.
4. Keep production activation open until that runtime has real acceptance evidence. If something fails, set its enable flag to `false` and rebuild/redeploy; removing a DSN also disables initialization. Do not change application access, budgets, retry policies or monitoring privacy controls to make a check pass.

## References

- [Sentry organization projects](https://fmazurkiewicz.sentry.io/settings/projects/)
- [Render environment variables](https://render.com/docs/configure-environment-variables)
- [Vercel environment variables](https://vercel.com/docs/environment-variables)
- [Sentry CI token scopes](https://docs.sentry.io/api/permissions/)
