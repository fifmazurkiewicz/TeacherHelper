# Verification evidence — TeacherHelper

Reviewed comparison base: `9855bd50605c04a61245cd1ab6eadfcc1e264e1d`. Implementation is limited to Sentry adapters, entrypoint wiring, failure-safe workflow reporting, SDK dependencies, tests, CI and documentation. Original unrelated local work is excluded; Reelcut uses an isolated copy of origin/main and is never merged into the owner's local checkout.

## Local checks

Backend: **91 passing**. Frontend: 5 Node privacy tests; TypeScript lint and Vite production build passed. Required applicable lint checks passed. Optional repository-wide format checks expose pre-existing formatting gaps; these are not CI gates and unrelated files were preserved.

Focused monitoring command: `cd backend && python -m pytest tests/test_sentry_monitoring.py -q`. Tests use synthetic sentinel content and actual SDK envelopes captured by an in-memory transport; no ingestion call is made. They inspect nested fields/attachments, expected denials/cancellation, duplicate reporting, disabled/invalid configuration, initialization failure and transport outage. Python metrics/log/transaction APIs are explicitly invoked and flushed, asserting zero outgoing envelopes.

## Regression strength

On 2026-11-01 a real Python SDK regression failed while metrics/logs/transactions could bypass the error filter, then passed after explicit dropping callbacks were added. A representative JavaScript filter-removal experiment in TeacherHelper failed its actual-envelope privacy checks, then passed with the original filter restored. These representative mutation checks are not claimed as per-runtime live tests. Each application runs its own intact SDK regression suite.

## Review and limitations

Independent source reviewers: `/root/sdk_backend_final_review` and `/root/sdk_frontend_final_review` (frontend where applicable). Corrective Python review: approve. Frontend review: approve for source integration. Findings and fixes: [canonical decisions](reviews/review-decisions.md); [review report](reviews/implementation-review.md).

Graft runtime was unavailable (`npx --offline @nanonets/graft check`: package not cached), so focused rg/source inspection was used. No paid provider, production user data, hosted ingestion, authenticated source-map upload/resolution, browser-to-Sentry network delivery, APK/device behavior or native-payload acceptance was tested. Aide native crash telemetry stays off. No Render/Vercel variables or production flags were changed. Build upload paths are tested locally without a real token; upload authentication remains an activation gate.

GitHub publication/CI result will be added after the authorized push. ModelFabric stays local and has no remote CI gate.
