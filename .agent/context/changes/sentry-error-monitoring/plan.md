# TeacherHelper Sentry implementation plan

Owner-approved scope and task acceptance: [Sentry contract](../../../../docs/technical/sentry.md).

- [x] SENTRY-01: SDK entrypoints and opt-in configuration.
- [x] SENTRY-02: terminal failure reporting without domain/provider coupling.
- [x] SENTRY-03: actual envelope privacy, expected failures and outage tests.
- [x] SENTRY-04: deployment examples and private artifacts.
- [x] SENTRY-05: full relevant checks, deliberate privacy break, independent review and publication.
- [ ] SENTRY-06: owner environment setup and hosted/device acceptance (external; not completed by local tests).

Use the existing package manager and lock file. Keep unrelated working changes out of the commit. Reuse the official SDK and small entrypoint adapters, with no monitoring service framework or dependency on agent-toolkit at runtime.
