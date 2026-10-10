---
name: implementation
description: Use to execute an approved change plan interactively while preserving a canonical progress record and verification evidence.
---

# Implementation

Read the approved plan, `progress.md`, review findings, project instructions,
and relevant Graft knowledge; use focused `rg` if Graft is unavailable. Make
only changes that satisfy accepted plan criteria. Update `progress.md` as each
stage completes, then synchronize the derived change board. Write commands,
outcomes, changed surfaces, and remaining risks to `evidence.md`.

When returning a review finding to implementation, use its canonical
`reviews/review-decisions.md` entry. Keep its follow-up, status, and evidence
link synchronized with `progress.md`; regenerate the decision board only after
the Markdown record changes.

Stop for a material plan or architecture mismatch instead of silently
expanding scope. Keep approvals, secrets, network access, and manual work
within project and environment policy. Hand off completed work to
implementation review.
