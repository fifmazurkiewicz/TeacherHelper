# Review decisions

Canonical record for this change. Owner: implementation maintainer (Codex) for fixes; Filip for later hosting/device acceptance. Generated board is a derived view.

## REV-002

- Finding: [implementation-review.md — REV-002](implementation-review.md#rev-002--retain-safe-source-map-debug-ids)
- Severity: medium
- Impact: security/privacy, correctness or operations
- Decision: Fix now
- Owner: implementation maintainer (Codex)
- Rationale: Preserve validated sourcemap Debug IDs and sanitized matching code_file values; actual SDK envelope and field-filter regressions cover the association.
- Status: verified
- Follow-up: [SENTRY-05 review and publication](../plan.md)
- Evidence: [actual local checks and regression evidence](../evidence.md)

## REV-003

- Finding: [implementation-review.md — REV-003](implementation-review.md#rev-003--exclude-expected-js-cancellations)
- Severity: medium
- Impact: security/privacy, correctness or operations
- Decision: Fix now
- Owner: implementation maintainer (Codex)
- Rationale: Drop known cancellation names including DOMException AbortError; real SDK regression expects zero envelopes.
- Status: verified
- Follow-up: [SENTRY-05 review and publication](../plan.md)
- Evidence: [actual local checks and regression evidence](../evidence.md)

## REV-005

- Finding: [implementation-review.md — REV-005](implementation-review.md#rev-005--keep-teacherhelper-job-imports-and-catch-indentation-valid)
- Severity: high
- Impact: security/privacy, correctness or operations
- Decision: Fix now
- Owner: implementation maintainer (Codex)
- Rationale: Correct future-import ordering and callback placement. Real chat-job regression persists failure with both a functioning and an offline reporter.
- Status: verified
- Follow-up: [SENTRY-05 review and publication](../plan.md)
- Evidence: [actual local checks and regression evidence](../evidence.md)

## REV-007

- Finding: [implementation-review.md — REV-007](implementation-review.md#rev-007--block-non-error-python-products-explicitly)
- Severity: high
- Impact: security/privacy, correctness or operations
- Decision: Fix now
- Owner: implementation maintainer (Codex)
- Rationale: SDK 2.73 ignores enable_metrics=False. Remove it and explicitly drop metrics, logs and transactions. A real flushed-envelope regression failed before this fix and passes after it; each runtime contains the regression.
- Status: verified
- Follow-up: [SENTRY-05 review and publication](../plan.md)
- Evidence: [actual local checks and regression evidence](../evidence.md)

