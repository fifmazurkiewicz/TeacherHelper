---
name: planning-boards
description: Use when a product roadmap, milestone plan, or active change needs a maintained Kanban view.
---

# Planning Boards

Make roadmap and change status legible without creating a second source of
truth. Use the existing `diagram-design` skill to render self-contained HTML
and inline-SVG Kanban diagrams.

## Sources and outputs

| Scope | Canonical source | Derived board |
| --- | --- | --- |
| Product | `docs/roadmap.md` | `docs/roadmap-kanban.html` |
| Active change | `plan.md` and `progress.md` | `.agent/context/changes/<change-id>/plan-kanban.html` |
| Review findings | `reviews/review-decisions.md` | `reviews/review-decisions-kanban.html` |

The Markdown records are the source of truth. A board must show the source
files and generation date, but it must never become the only place that
records a decision, scope change, blocker, dependency, or completion.

Review-decision cards are one per non-informational finding. Use columns
**Fix now**, **Fix differently**, **Skip**, and **Record as lesson**; each card
shows its stable ID, severity, impact, owner, status, and canonical reference.
Do not create a decision card for an information-only note.

## Board contract

Use these columns: **Planned**, **Ready**, **In progress**, **Blocked**, and
**Done**. Roadmap cards are milestones. Change-board cards are independently
verifiable plan tasks. Each card names its outcome, status, dependencies or
blocker when relevant, and a concise reference to its source record.

Create or update a roadmap board when the product has multiple milestones.
Create a change board when a meaningful change gains an approved plan. Update
the canonical record first, then its board whenever work starts, completes,
blocks, or is materially replanned. Keep useful completed milestones compact;
preserve a completed change board with its archived change record.

## Replanning and review

A material scope, architecture, dependency, or acceptance-criterion mismatch
is not a normal card move. Stop implementation, update the affected canonical
plan and roadmap, regenerate the affected board, and repeat plan review before
resuming. Implementation review must reconcile every displayed status with
`progress.md` and evidence.

## Rendering boundaries

Render a static, self-contained HTML diagram; do not add a live dashboard,
external project-management service, or runtime dependency. Apply the
`diagram-design` style-guide gate before a project's first board, and do not
overwrite unrelated documentation.
