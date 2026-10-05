---
name: python-service-architecture
description: Use when creating or materially restructuring a Python service, API, worker, CLI, or package that needs clear delivery, application, domain, and infrastructure boundaries.
---

# Python Service Architecture

Use the project's established package root. For a new installable package,
prefer `src/<package_name>/`; do not move an existing project solely to match
this shape.

Keep dependency direction inward:

```text
delivery (API / CLI / worker) -> application -> domain
infrastructure ----------------> application / domain contracts
```

- Delivery adapters translate requests, commands, and events; they do not own
  business decisions.
- Application code orchestrates use cases and may depend on domain code.
- Domain code contains business rules and must not import FastAPI, an ORM,
  HTTP clients, provider SDKs, or environment configuration.
- Infrastructure provides database, storage, and provider implementations;
  wire those concrete implementations in the composition root (for example,
  `main.py` or a CLI entrypoint).
- Keep unit tests independent of delivery and external infrastructure. Put
  adapter, database, and full-boundary tests under integration tests.

Add a directory or abstraction only when there is a real second concern or
implementation. Do not create empty Clean Architecture layers, generic base
repositories, or interfaces for a single implementation. Preserve documented
project-specific exceptions.
