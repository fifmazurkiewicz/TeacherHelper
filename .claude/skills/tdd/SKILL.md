---
name: tdd
description: Use when a testable behavior is added or changed to establish a failing behavioral test before implementation.
---

# Test-Driven Development

Read the approved plan, frame, research, and Graft knowledge; use focused `rg`
if Graft is unavailable. Derive expected behavior from requirements, not the
existing implementation. Write a focused failing test before altering
testable behavior, make the smallest implementation pass, then refactor only
with the test green.

Deliberately break the protected behavior once to prove the test turns red.
Record red, green, and deliberate-break evidence in `evidence.md` and update
`progress.md`. Do not weaken a test, replace behavioral assertions with mocks,
or claim TDD for a behavior the test cannot detect.
