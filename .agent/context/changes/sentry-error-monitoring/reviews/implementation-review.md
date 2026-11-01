# Implementation review — TeacherHelper

Comparison base: `9855bd50605c04a61245cd1ab6eadfcc1e264e1d`. Independent read-only reviews covered the intended diff and new files, actual entrypoints, swallowed failures, SDK filtering, dependency/build boundaries and observed tests. Reviewers did not edit code. Source integration outcome: **approve after the fixes below**. Publication CI and hosted/device acceptance are separate gates.

## Coverage

SENTRY-01–04: covered by reviewed source, examples and local behavioral tests. SENTRY-05: source review and local checks accepted; publication result pending. SENTRY-06: explicitly open. Security/privacy: technical allowlist, EU-only DSNs, explicit opt-in, no non-error products, and no user payloads. Convention alignment: SDK at delivery edges and injected callbacks for domain/application failures. Trading risk logic and original local WIP are preserved.

## Findings and dispositions

### REV-002 — Retain safe source-map Debug IDs

Severity: medium. Preserve validated sourcemap Debug IDs and sanitized matching code_file values; actual SDK envelope and field-filter regressions cover the association. Disposition: [Fix now — verified](review-decisions.md#rev-002).

### REV-003 — Exclude expected JS cancellations

Severity: medium. Drop known cancellation names including DOMException AbortError; real SDK regression expects zero envelopes. Disposition: [Fix now — verified](review-decisions.md#rev-003).

### REV-005 — Keep TeacherHelper job imports and catch indentation valid

Severity: high. Correct future-import ordering and callback placement. Real chat-job regression persists failure with both a functioning and an offline reporter. Disposition: [Fix now — verified](review-decisions.md#rev-005).

### REV-007 — Block non-error Python products explicitly

Severity: high. SDK 2.73 ignores enable_metrics=False. Remove it and explicitly drop metrics, logs and transactions. A real flushed-envelope regression failed before this fix and passes after it; each runtime contains the regression. Disposition: [Fix now — verified](review-decisions.md#rev-007).

