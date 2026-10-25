---
name: implementation-review
description: Use after implementation or when asked to review code changes, before archive or merge.
---

# Implementation Review

Read the available plan, progress, evidence, diff, and relevant Graft knowledge; use
focused `rg` if Graft is unavailable. Write
`reviews/implementation-review.md` with findings grouped by severity, plan
coverage, test evidence, security and privacy impact, convention alignment,
and a clear approve/revise outcome. For a standalone code review without a
change-context folder, report in chat or the requested location; assess the
diff against repository instructions and tests without inventing plan records.

## Code review

Use the current AI session and tools already available in the repository.
This skill requires no additional service, account, CLI, or installation.

1. Inspect Git status, the intended diff, and in-scope new files. Confirm the
   actual comparison base; for branch work, review from its verified merge
   base. Keep unrelated work outside the review.
2. When subagents are available, ask a fresh reviewer agent to review without
   editing code. Give it the task, acceptance criteria, base/scope, repository
   instructions, relevant files, and observed test results. Let it inspect the
   implementation independently rather than supplying the author's verdict.
   When subagents are unavailable, perform an explicit second review pass and
   state that the review was not independent.
3. Trace changed behavior through callers, contracts, failure paths, and tests.
   Check correctness, regressions, security/privacy, error handling, repository
   conventions, and missing coverage, including the required test depth for
   touched risks when `docs/testing-strategy.md` exists, and tests that assert
   implementation details, recompute expected values with the code's own logic,
   or duplicate one another. Separate evidence-backed defects from
   optional preferences; report actionable findings with severity, file/line,
   impact, and a concrete fix or verification step.
4. Run the smallest relevant checks already available within the authorized
   environment. Record actual results and gaps; unavailable tools or unrun
   tests remain disclosed limitations, not passing checks. Do not install
   software or initiate third-party reviews as part of this skill.
5. Feed findings into the decision workflow below, return fixes to
   implementation, and review the updated diff and verification evidence after
   fixes. Record the reviewed base/scope and whether a separate reviewer was
   used. An empty finding list alone does not establish adequate coverage.

## Review decisions

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
