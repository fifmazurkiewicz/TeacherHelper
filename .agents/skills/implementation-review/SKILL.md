---
name: implementation-review
description: Use after implementation to assess plan fidelity, evidence, tests, safety, and repository conventions before archive or merge.
---

# Implementation Review

Read the plan, progress, evidence, diff, and relevant Graft knowledge; use
focused `rg` if Graft is unavailable. Write
`reviews/implementation-review.md` with findings grouped by severity, plan
coverage, test evidence, security and privacy impact, convention alignment,
and a clear approve/revise outcome.

For every non-informational finding, invoke `review-decisions` and record its
disposition in `reviews/review-decisions.md` before determining the outcome.
Generate the derived `reviews/review-decisions-kanban.html` after its
canonical record changes. A finding without a valid disposition is revise.

When planning boards exist, reconcile every displayed status with `plan.md`,
`progress.md`, and evidence. A mismatch is a revise outcome: update canonical
records first, then regenerate the affected board.

Require evidence for every accepted criterion. Do not edit implementation as
part of review or archive a change with unresolved blockers unless a human
owner explicitly accepts them as a documented Skip with a re-evaluation
trigger. Return concrete fixes to implementation.
