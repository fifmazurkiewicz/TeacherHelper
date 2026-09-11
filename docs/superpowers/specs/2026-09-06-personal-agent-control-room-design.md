# Personal agent control room — design

**Date:** 2026-09-06  
**Scope:** Personal operating layer across all coding repos. **Not** a TeacherHelper product feature. No TeacherHelper application code in v1 except optional `AGENTS.md` / CI / workflow files when this repo is wired in.

## Goal

One human (the owner) plans work on a multi-repo GitHub Projects board and, while away, starts accurate jobs. Agents are the team. Work merges to `main` only when tests and change docs pass; Vercel/Render then deploy from `main`. The owner opens a laptop or the board only to describe tasks, analyze with an assistant, smoke-test production, or unblock a card.

## Actors

| Actor | Role |
|---|---|
| Owner | Only human. Writes issues, analyzes, smoke-tests prod, unblocks. Own coding still happens in Cursor when chosen. |
| Team | Agents (not other humans). |
| Default worker | Cursor Cloud Agent, one git repo per run. |
| Alternate worker | Any other agent that obeys the same Done gate. |
| Assistant | Cursor chat or Slack thread used to clarify a Blocked issue or to analyze — not a second source of truth for tickets. |
| Dispatch | GitHub Action: issue labeled `ready` → Cursor Cloud Agents API. Slack `@Cursor` is the manual/phone path. |

## Architecture

Three layers. Slack is the remote and the ping channel. **GitHub Issues + one Projects v2 board** are the source of truth.

| Layer | Job | v1 tool |
|---|---|---|
| Board | All repos, sprints, status | GitHub Projects v2 (“Control Room”) |
| Cards | Work items | GitHub Issues (in the **target** repo) |
| Dispatch | Start a worker unattended | `.github/workflows/cursor-triage.yml` on label `ready` |
| Remote | Phone start / status / notify | Slack `@Cursor` + GitHub Slack app |
| Gate | Who may land on `main` | Branch protection: **required CI checks only** (no required human approval) |
| Worker | Implement, PR, satisfy Done gate | Cursor Cloud Agent |
| Ship | Production | Vercel / Render from `main` |

```text
Owner writes Issue (target repo) ── add-to-project Action ──► Control Room board
        │
        ▼
   Inbox / Backlog
        │
        ▼
   label `ready`  (or Slack @Cursor)
        │
        ▼
   cursor-triage.yml ──► Cloud Agent (this repo) ──► Doing
        │
        ├─ type: audit ──► report on the issue ──► Done (no merge)
        │
        ├─ fail tests / missing docs / no CI ──► Blocked
        │         │
        │         └── Assistant clarifies issue ──► remove Blocked, label `ready` again
        │             (no silent retry)
        │
        └─ GWT tests + CI green + change docs
                    │
                    ▼
           enable auto-merge / merge main
                    │
                    ▼
           Vercel / Render deploy
                    │
                    ▼
           Slack: PR, summary, prod URLs, English checklist + logs
                    │
                    ▼
           Owner smoke-tests prod (optional) ──► Done
```

## Board model

- **One** GitHub Project v2 (e.g. “Control Room”), linked to every participating repo.
- New issues appear on the board via a **per-repo GitHub Action** (`actions/add-to-project`), not the Project’s built-in Auto-add. GitHub Free allows **1** built-in auto-add workflow (already used on Langy); Pro/Team allow 5. That cap does not apply to Actions. Keep the Langy built-in workflow or replace it — do not plan on one built-in auto-add per repo.
- Views: one view filtered per repo; one global Table sorted by Priority, with Iteration visible.
- **Iteration** = sprint (e.g. 1 week). No Scrum ceremonies.
- **Priority** field: `P0` / `P1` / `P2`.
- Status columns: **Inbox → Ready → Doing → Blocked → Done** (map Project status; `ready` **label** is what starts the worker).
- Issue template (required body): job type, Given/When/Then, how to verify. Repo is implied by which repo the issue lives in.
- Job types (label or template field): `audit` | `test` | `integrate` | `implement` | `realize`.
- `implement` and `realize` use the same Done gate (`realize` = “just get it done”). `test` adds/fixes tests. `integrate` wires systems. `audit` reports only.
- Docs stay in each repo’s `docs/` and `AGENTS.md`. The Project does not copy documentation.

## Done gate (auto-merge)

A non-`audit` job may merge to `main` only when **all** are true:

1. Tests added or updated so the issue’s Given/When/Then would fail without the change.
2. That repo’s real CI is green (commands from that repo’s `AGENTS.md`).
3. PR body states what changed, why, and how to verify.
4. If API, config, or user-facing behavior changed: a short delta in `docs/` or an ADR.

Otherwise the issue stays **Blocked**. The worker must **not** merge a failing or undocumented PR.

**No CI on the repo → do not wire this repo; no auto-merge.**

`audit` never merges. Deliverable is a written report on the issue.

### How merge is allowed (fixes the guide contradiction)

Branch protection on `main`:

- Require a pull request.
- Require the real CI status checks to pass.
- **Do not** require a human review / owner approval. That would block unattended C.

The triage prompt must **not** say “never merge.” It must say: follow `AGENTS.md`; open a PR; **enable auto-merge** (or merge) **only** when the Done gate is satisfied; if not, comment why and stop.

GitHub auto-merge + required checks is the mechanism. The agent does not force-push to `main`.

Auto-merge to `main` **is** production deploy (Vercel/Render).

## After merge / after deploy

- Merge + deploy OK: issue → **Done**; Slack ping with title, repo, PR URL, summary, prod URLs, **short English checklist + logs**.
- Merge OK, deploy failed: issue → **Blocked**; ping with log links; owner/Assistant may revert the PR.
- Owner smoke-tests prod when they choose.

## Blocked

- Worker stops. No automatic retry loop.
- Owner talks with the Assistant (Slack or Cursor).
- Issue is corrected, Blocked cleared, `ready` applied again. Owner waits.

## Dispatch (per repo)

`.github/workflows/cursor-triage.yml` fires on `issues: labeled` when the label is `ready`. It calls the current Cursor Cloud Agents API (`cursor.com/docs/cloud-agent/api` — confirm `v0` vs `v1` before shipping) with `CURSOR_API_KEY` (repo secret), the issue title/body/URL, and `autoCreatePr: true`.

Slack `@Cursor` remains valid: per-project channel with `@Cursor settings` default repo. GitHub Slack app: `/github subscribe` and `/github issue create`.

Confirm API request shape on a throwaway issue before trusting a real repo.

## Requirements (Given / When / Then)

- **Given** an issue with type, GWT, and verify steps  
  **When** the owner adds label `ready` (or `@Cursor` on that issue)  
  **Then** a Cloud Agent runs in that repo and the Project item is Doing

- **Given** an `implement` / `test` / `integrate` / `realize` job whose GWT tests pass, CI is green, and change docs are present  
  **When** the worker finishes  
  **Then** the PR auto-merges to `main`, Vercel/Render deploy, Slack gets the English checklist + links, issue is Done

- **Given** a job whose tests fail, docs are missing, or the repo has no CI  
  **When** the worker finishes  
  **Then** no merge; issue is Blocked with a comment; no silent retry

- **Given** an `audit` issue  
  **When** the worker finishes  
  **Then** a report is on the issue; `main` is unchanged

- **Given** a Blocked issue  
  **When** the owner and Assistant agree on a clarified GWT and `ready` is applied again  
  **Then** a new worker run is allowed

- **Given** the owner is away  
  **When** they label `ready` from GitHub mobile or Slack, or `@Cursor`  
  **Then** work starts without opening the IDE

- **Given** the owner is at a laptop  
  **When** they work  
  **Then** they only need the Project/Issues or Cursor to write tasks, analyze, smoke-test prod, or unblock

## Error handling

| Failure | Behavior |
|---|---|
| CI red | Blocked; no merge |
| Missing GWT tests or change docs | Blocked; no merge |
| Repo has no CI | Do not enable triage / auto-merge |
| Worker cannot read the issue | Blocked; comment on the issue |
| Cursor API / Action fails | Issue stays Ready or Blocked with Action log link; no retry loop |
| Deploy fails after merge | Blocked; Render/Vercel logs; consider revert |
| Alternate worker used | Same Done gate |

## Testing this system (v1)

Wiring smoke (one repo first):

1. Throwaway issue, label `ready` → Action runs → Cloud Agent starts (`cursor.com/agents` or `@Cursor list my agents`).
2. Agent opens a PR; CI runs.
3. Deliberately failing test → **does not** merge; Blocked + reason.
4. Green run with PR body + docs delta → **does** merge and deploy; Slack English checklist + prod URL.
5. `audit` issue → no merge.
6. Blocked issue does not retry until `ready` is applied again.

Only after these pass on one repo, roll out to the next.

## Out of scope (v1)

- Linear
- Custom Kanban web app
- Hermes / Grok as the coding worker
- Discord as source of truth
- Telegram (later)
- One agent with every repo checked out
- Auto-retry on failure
- Required human PR approval (would break C)
- Weekly standup / `#board-meeting` idea-evaluation automations (Part 10 of the setup guide)
- GitHub Projects MCP (nice later: “add a P1 issue from Cursor chat”)
- Per-repo standup persona automations
- Changing how the owner writes code in Cursor
- TeacherHelper product features

## Decisions

| Date | Decision | Why |
|---|---|---|
| 2026-09-06 | Linear + Slack + Cloud Agent (superseded) | First pass; owner later preferred GitHub-native board |
| 2026-09-06 | **Board = GitHub Projects v2 + Issues, not Linear** | Owner chose this setup; Issues + `ready` + Actions + branch protection live in one place |
| 2026-09-06 | Dispatch = label `ready` → Actions → Cloud Agents API; Slack `@Cursor` also OK | Unattended start without a custom app |
| 2026-09-06 | Branch protection: required CI, **no** required human review | Needed for auto-merge C |
| 2026-09-06 | Worker prompt: merge/auto-merge only if Done gate passes (not “never merge”) | Guide Part 3/6/11 contradicted C |
| 2026-09-06 | Worker is swappable; Cloud Agent is default | Accuracy is the gate; owner still codes in Cursor |
| 2026-09-06 | Auto-merge to `main` when GWT tests + CI + change docs pass | Unattended “job is done” |
| 2026-09-06 | `main` deploy is automatic (Vercel/Render) | Merge is the ship |
| 2026-09-06 | Post-deploy checklist is short English + logs | Owner correction |
| 2026-09-06 | Team = agents only | Solo operator |
| 2026-09-06 | Docs stay in git | Avoid stale copies on the board |
| 2026-09-06 | Standups, board-meeting bots, Projects MCP = not v1 | Extra ceremony; add after the merge loop works |
| 2026-09-06 | Spec lives in TeacherHelper `docs/superpowers/specs/` as session SoT only | Chat started here |
| 2026-09-06 | Board ingest = `actions/add-to-project` per repo, not Project Auto-add | Free = 1 built-in auto-add (Langy used it); Actions scale to N repos |

## v1 setup

**Once total:** Project v2 + Priority + Iteration + views; `ADD_TO_PROJECT_PAT`; Cursor API key; Slack `@Cursor`; GitHub Slack app.

**Per repo:** real CI; `AGENTS.md` (build/test + Done gate); Project access; branch protection (CI, no required reviewer); Cursor GitHub grant; `CURSOR_API_KEY` + `ADD_TO_PROJECT_PAT`; `cursor-triage.yml` + `add-to-control-room.yml`; issue template; optional Slack channel + `/github subscribe`.

**Adding another repo:** CI + `AGENTS.md` → Project access → protection → Cursor grant → both secrets → copy both workflows → Slack → smoke test. Do not add another built-in Auto-add.

Confirm Cloud Agents API shape at https://cursor.com/docs/cloud-agent/api/endpoints (`POST /v1/agents`, public beta) before relying on the triage workflow.
