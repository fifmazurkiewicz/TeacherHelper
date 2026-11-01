# Progress

2026-11-01 — SENTRY-01–04 implemented and locally verified. Official SDKs are wired into the real entrypoints, technical-only filtering is tested using actual SDK envelopes, and per-runtime configuration examples/runbooks are present.

SENTRY-05: local checks and independent source review complete; publication and resulting GitHub Actions are pending. ModelFabric is local-only and has no publication step. SENTRY-06 remains open: owner supplies hosting/build variables, redeploys and accepts synthetic events per runtime. Native crash collection remains disabled in Aide. No production activation is claimed.

Canonical task descriptions: [Sentry contract](../../../../docs/technical/sentry.md). [Evidence](evidence.md). [Review decisions](reviews/review-decisions.md).
