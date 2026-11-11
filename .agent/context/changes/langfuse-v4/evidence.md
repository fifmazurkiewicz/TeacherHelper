# Verification evidence

- Full backend suite: 95 passed; existing Alembic path_separator deprecation warning only.
- Ruff check: passed. Poetry check --lock: passed (existing manifest deprecation warnings).
- Real SDK 4.15.5 loaded from installed cache; Sentry 2.73.0 from installed cache. No real keys, application content or cloud ingestion used in tests.
- Lock resolved by Poetry 2.3.2 using copied Poetry cache and exact SDK metadata from installed distribution. Artifact SHA256 hashes verified against https://pypi.org/project/langfuse/4.15.5/#files. No package versions changed except Langfuse; obsolete OpenAI-only dependencies removed by resolver. Some constraints/markers normalized by Poetry.
- Deliberate regressions: removing the v4 header makes transport test fail; removing context propagation makes isolation test fail. Original source restored and full suite passed afterward.
- git diff --check passed. Frontend unchanged; local frontend dependencies unavailable, build deferred to CI.

| Test | Expected behavior | Regression detected / breaking change |
| --- | --- | --- |
| generations_preserve_usage_and_isolate_conversations | Each generation has its own user/session and exact token counts; no context after two conversations stays empty | Removing context propagation or token mapping |
| missing_credentials_disable_telemetry | Optional integration reports missing keys without network access | Mandatory credentials or unconditional initialization |
| chat_completion_emits_generation_with_session | Chat observations retain session, output and token counts | Breaking completion observation mapping |
| default_transport_uses_v4_ingestion | Real SDK exporter sends protobuf observation to OTLP endpoint with v4 header | Removing additional_headers; deliberately verified |

Independent reviewer approved final code and ran five focused tests (including existing context test). Hosted CI, deploy logs and Cloud Action required verification remain separate rollout checks.
