---
name: review-decisions
description: Use when an implementation or plan review produces findings that need an explicit disposition, risk acceptance, or reusable lesson.
---

# Review Decisions

Turn review findings into durable, accountable decisions without turning a
review report or a visual board into a competing execution record.

## Canonical record and board

For each review round with non-informational findings, maintain
`reviews/review-decisions.md`. It is the source of truth. Generate or update
`reviews/review-decisions-kanban.html` only after its Markdown record changes,
using `diagram-design` to create static self-contained HTML with inline SVG.
The board shows source file and generation date; it is never the only place a
decision or its rationale exists.

Use one stable heading per finding, for example `## REV-001`, with:

```markdown
## REV-001 — concise finding title

- Finding: `implementation-review.md#...`
- Severity: critical | high | medium | low
- Impact: user, security/privacy, correctness, operations, or plan fidelity
- Decision: Fix now | Fix differently | Skip | Record as lesson
- Owner: role or named human responsible for the decision
- Rationale: why this disposition is appropriate
- Status: open | in progress | verified | accepted | archived
- Follow-up: link to the plan/progress task or exact manual action
- Evidence: link to verification, acceptance, or review evidence
- Re-evaluation trigger: required for Skip
```

Information-only notes remain in the review report and do not create a record
or a board card. Keep cards small; split a board by review round when it would
exceed the Kanban complexity budget.

## Decision contract

| Decision | Required result |
| --- | --- |
| Fix now | Return a concrete fix to implementation; mark verified only with evidence. |
| Fix differently | Update plan/progress first; repeat plan review before implementation if the alternative is material. |
| Skip | A human owner explicitly accepts the risk, with rationale and re-evaluation trigger. The reviewer cannot select it alone. |
| Record as lesson | After archive, add only reusable, evidence-backed knowledge to Graft. It never substitutes for a required fix. |

An approve outcome requires a disposition for every non-informational finding.
Open, in-progress, or unverified Fix-now/Fix-differently records require a
revise outcome. Skip is an accepted exception and remains visible in the
record and board.

## Synchronization

Link, rather than duplicate, execution state in `progress.md`, design choices
in `decisions.md`, and observed checks in `evidence.md`. A material alternate
solution or a finding that invalidates an acceptance criterion stops work for
replanning and plan review. At archive, preserve the decision record with the
change; do not create `lessons.md`.
