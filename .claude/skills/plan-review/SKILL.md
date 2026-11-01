---
name: plan-review
description: Use before implementation to review a change plan against its frame, research, decisions, contracts, and acceptance criteria.
---

# Plan Review

Read `frame.md`, `research.md`, `decisions.md`, and `plan.md`; query Graft for
relevant conventions or use focused `rg` if unavailable. Write
`reviews/plan-review.md` with scope gaps, untested acceptance criteria,
contract impact, unsafe assumptions, and an approve/revise outcome.

## Bug-fix diagnosis and proposed remedy

For a plan addressing a reported malfunction, include a causal assessment:

- **Observation and expectation:** separate the reported symptom, assumed cause,
  and requested solution. Identify the expected behavior and its product or
  requirement source; a report alone does not establish a bug.
- **Evidence and cause:** trace the relevant flow, including writes, reads,
  filters, state and presentation where involved. Cite reproducible observations,
  code, tests or sanitized events. Distinguish a supported cause from a
  hypothesis and identify credible alternatives still consistent with the facts.
- **Remedy fit:** explain how the planned change addresses that cause while
  preserving intended behavior, access boundaries and failure handling. Assess
  a proposal from a user, teammate or AI against the same evidence; confidence
  or implementation feasibility does not establish causal fit. Check whether
  it merely hides an error or bypasses an intentional rule.
- **Regression evidence:** require a check of the observable failure that would
  fail before the fix and pass afterward, plus preservation checks warranted by
  the risk. A test that only verifies the proposed mechanism was called is not
  evidence that the reported problem is solved.

If the cause is unverified or the expected product behavior is unclear, return
**revise** for the proposed fix and name the smallest discriminating check or
owner clarification. A bounded plan to gather evidence may be approved within
its own authorized scope; its eventual fix must return for review. Revisit the
frame or decisions when new evidence contradicts them. Scale investigation to
the uncertainty and risk; do not invent evidence or require installing telemetry.

Do not implement the plan while reviewing it. A material gap returns the plan
to its author. An approved plan must identify manual versus automated work,
verification commands, and evidence expected from implementation.

If a prior review finding requests Fix differently, verify that its canonical
review-decision record links to the amended plan and that the material change
is reviewed before implementation resumes.
