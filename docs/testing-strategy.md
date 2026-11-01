# Testing strategy

Draft Sentry risk map. Scope: `technical/sentry.md`, owner-approved privacy/errors-only contract, existing entrypoints and `AGENTS.md`. Unconfirmed ratings are conservative and never lower required depth; this change does not claim a complete product-wide audit.

| User/business scenario | Impact | Likelihood | Required tests | Source |
| --- | --- | --- | --- | --- |
| Private application content or credentials leave the app | High | Medium (new integration; assumption) | Real SDK envelope integration, nested sentinels, deliberate filter-removal failure | Approved privacy scope |
| Monitoring failure prevents app operation | High | Medium (external service) | Missing, invalid, disabled configuration and init/transport outage integration | Fail-safe requirement |
| Background failure is silent or duplicated | Medium | Medium (caught errors) | Terminal logged error and duplicate capture integration | Existing jobs |
| Expected denials/cancellation/budget outcomes flood monitoring | Medium | Medium | Expected-error regressions | Existing authorization and spend controls |
| Untrusted URLs, paths or exception fields disclose user data | High | Medium | Actual emitted payload attack cases | Privacy scope and AGENTS untrusted-data rule |

## Evidence and existing profile

pytest/FastAPI TestClient backend and existing Vitest frontend. Component commands are in AGENTS.md and package manifests. Existing suites remain authoritative.

## QA phases and useful tests

Requirements review → red regression → implementation → green tests → deliberate privacy break → independent review → CI → separate staging activation. Use SDK transport/API/browser integration; no paid-provider or load test is needed for this bounded adapter.

## Agent quality boosts

Inspect actual envelopes, use sentinel strings in nested input, and ask a fresh reviewer to trace failure paths. Mock only the external transport, not capture/init behavior.

## Cookbook

Backend: `tests/test_sentry_monitoring.py`, run `python -m pytest tests/test_sentry_monitoring.py -q` from backend. Use synthetic data and an in-memory Sentry Transport. Frontend uses existing Vitest transport tests plus lint/types/build. Record regressions and actual results in the Sentry task evidence; hosted activation stays open until a real synthetic event is verified.
