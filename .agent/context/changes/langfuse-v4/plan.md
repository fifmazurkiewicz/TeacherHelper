# Langfuse Cloud v4 compatibility

Source: owner migration email (cutover 2026-11-16), https://langfuse.com/faq/all/upgrade-to-langfuse-v4 and Python v3→v4 upgrade guide.

Decision: pin Python SDK 4.15.5 (cached, supported >=4.7.0); keep existing observation API, context propagation and opt-in credentials. Update both Poetry CI and requirements.txt Docker paths. No new telemetry, configuration, architecture or database migration. Audit repository for legacy reads, datasets, scores and exporters. Cloud-side evaluators/integrations need separate dashboard verification.

1. Update manifests and resolve lock without unrelated upgrades.
2. Exercise real SDK via in-memory exporter with synthetic data: generation attributes, token counts, conversation isolation and optional disabled operation.
3. Review diff independently; run backend suite/lint, then publish and verify CI/deploy if available.

| Failure scenario | Impact | Likelihood | Verification | Source |
| --- | --- | --- | --- | --- |
| Observations disappear after cutover | Medium | High (announced deadline) | Real SDK exporter integration, both manifests/lock | Migration guide/email |
| Conversation/user attributes mix across calls | High | Medium | Sequential synthetic conversations and no-context call | Sessions design, access/privacy rule |
| Missing optional credentials disrupt application | High | Low | Disabled telemetry regression | Existing optional configuration |
| User input causes propagated attributes to leak to another conversation | High | Medium | Isolation assertions on emitted spans | AGENTS untrusted input/privacy |

Ratings are conservative, unconfirmed; none lower test depth.
