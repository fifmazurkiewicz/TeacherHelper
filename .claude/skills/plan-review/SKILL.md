---
name: plan-review
description: Use before implementation to review a change plan against its frame, research, decisions, contracts, and acceptance criteria.
---

# Plan Review

Read `frame.md`, `research.md`, `decisions.md`, and `plan.md`; query Graft for
relevant conventions or use focused `rg` if unavailable. Write
`reviews/plan-review.md` with scope gaps, untested acceptance criteria,
contract impact, unsafe assumptions, and an approve/revise outcome.

Do not implement the plan while reviewing it. A material gap returns the plan
to its author. An approved plan must identify manual versus automated work,
verification commands, and evidence expected from implementation.

If a prior review finding requests Fix differently, verify that its canonical
review-decision record links to the amended plan and that the material change
is reviewed before implementation resumes.
