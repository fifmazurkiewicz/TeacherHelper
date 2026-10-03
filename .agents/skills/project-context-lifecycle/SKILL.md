---
name: project-context-lifecycle
description: Use when a meaningful project change needs persisted context from problem framing through review and archive.
---

# Project Context Lifecycle

Use one active `<change-id>` at a time. Keep its history under
`.agent/context/changes/<change-id>/`; do not use this skill for a tiny,
already-understood edit that needs no durable change record.

## Layout

```text
.agent/context/
  foundation/                 # optional stable, explicit project contracts
  changes/<change-id>/
    frame.md  research.md  decisions.md  plan.md  progress.md  evidence.md
    reviews/
  archive/<change-id>/
```

`progress.md` is the canonical execution state. Record facts in `research.md`,
choices and rationale in `decisions.md`, and observed verification in
`evidence.md`; do not merge their purposes.

## Lifecycle

`problem-framing -> technical-research -> decisions -> plan -> plan-review ->
implementation / tdd -> evidence -> implementation-review -> archive`.

Archive only after implementation review is complete. Move the whole change
directory to `archive/<change-id>/`; do not delete evidence.

## Durable knowledge

Query Graft before research, planning, implementation, and review for relevant
project knowledge. After archive, add only reusable, evidence-backed knowledge
to Graft under the project's policy. Never create `lessons.md`: it would be a
second long-term store. If Graft is unavailable, use focused `rg` queries and
state that limitation. Never store secrets, personal data, or transient logs.
