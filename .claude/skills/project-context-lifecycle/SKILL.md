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
    plan-kanban.html       # derived from plan.md and progress.md
    reviews/               # review report, decision record and derived board
  archive/<change-id>/
```

`progress.md` is the canonical execution state. Record facts in `research.md`,
choices and rationale in `decisions.md`, and observed verification in
`evidence.md`; do not merge their purposes.

When a review produces non-informational findings, keep their canonical
dispositions in `reviews/review-decisions.md` and its derived visual view in
`reviews/review-decisions-kanban.html`. These records link to, rather than
replace, plan, progress, decisions, and evidence.

For a product with multiple milestones, maintain `docs/roadmap.md` and its
derived `docs/roadmap-kanban.html`. For each meaningful change, create and
synchronize `plan-kanban.html` only after the plan exists. The Markdown
records are the source of truth; the boards are derived views.

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
