---
name: goal-implement
description: Use for non-interactive execution of an approved plan when automated work, safety boundaries, and quality gates are explicit.
---

# Goal Implementation

This is the autonomous counterpart to `implementation`, not a permission
escalation. Start only with an approved plan that identifies automated and
manual steps, allowed file scope, network and secret boundaries, verification
commands, and acceptance criteria. Read relevant Graft knowledge first; use
focused `rg` if Graft is unavailable.

For each automated stage, update `progress.md`, run its quality gates, record
evidence, and commit only after green verification. Return manual steps as a
human checklist. A minor file move or renamed symbol may be reported and
adapted; a missing dependency, architectural conflict, ambiguous acceptance
criterion, or out-of-scope change is structural drift and must produce STOP.

Attempt to repair one failed quality gate at most two repair attempts. After a
second failure, emit STOP with the gate output, attempted fixes, and next
human decision. Never bypass tests, broaden permissions, expose secrets, or
mark manual work complete.
