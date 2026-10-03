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

Require evidence for every accepted criterion. Do not edit implementation as
part of review or archive a change with unresolved blockers unless a human
owner explicitly accepts them. Return concrete fixes to implementation.
