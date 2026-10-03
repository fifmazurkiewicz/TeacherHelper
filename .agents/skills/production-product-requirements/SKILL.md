---
name: production-product-requirements
description: Use when approved product shaping decisions need a clear production-ready PRD before technical implementation planning.
---

# Production Product Requirements

Turn approved solution-shaping decisions into an unambiguous product contract.
It defines what production behavior must achieve, not how source files should
be changed.

## Required PRD sections

1. Problem and context.
2. Goals and non-goals.
3. Users and end-to-end flows.
4. Functional requirements.
5. Edge cases, error states, and recovery behavior.
6. Constraints: business, legal, operational, security, privacy, accessibility,
   performance, and integrations where relevant.
7. Acceptance criteria that can be verified.
8. Risks, dependencies, and open questions with an owner or decision needed.

Use approved validation and brainstorming outputs; do not reopen them without a
new contradiction. Do not prescribe files, classes, migrations, APIs, or a
step-by-step engineering plan.

## Happy path

```text
idea-validation -> brainstorming -> production-product-requirements
-> writing-plans -> implementation/review
```

Once the PRD is approved, use `writing-plans` for the technical plan. If the
product decision is not yet shaped, return to `brainstorming`; if the problem
itself lacks evidence, return to `idea-validation`.
