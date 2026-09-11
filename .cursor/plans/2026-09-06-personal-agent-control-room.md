# Personal Agent Control Room Implementation Plan

> **For agentic workers:** This plan is mostly GitHub / Cursor / Slack dashboard work by the owner. Do not invent secrets. Do not commit `.env`. REQUIRED SUB-SKILL if adding repo files: `superpowers:executing-plans`.

**Goal:** Wire one GitHub Projects v2 board + `ready` → Cursor Cloud Agent + CI auto-merge + Vercel/Render + Slack, matching `docs/superpowers/specs/2026-09-06-personal-agent-control-room-design.md`.

**Architecture:** Issues in each target repo are the cards. One Project (“Control Room”) is the board. Label `ready` runs `.github/workflows/cursor-triage.yml`, which POSTs `https://api.cursor.com/v1/agents`. Branch protection requires CI only (zero human approvals). Green Done-gate PRs auto-merge to `main` and deploy.

**Tech Stack:** GitHub Projects v2, GitHub Actions, Cursor Cloud Agents API v1, Slack `@Cursor`, Vercel, Render.

## Global Constraints

- Board is GitHub Projects v2, not Linear.
- Auto-merge C: required CI checks; **no** required human review.
- Worker may auto-merge only when GWT tests + CI + change docs pass.
- `audit` never merges.
- No silent retry; Blocked → Assistant → label `ready` again.
- Post-deploy ping: short English checklist + logs.
- Team = agents only.
- Confirm API at https://cursor.com/docs/cloud-agent/api/endpoints before trusting curl (v1 is public beta).
- Do not put API keys in git.

---

### Task 1: Pick the first repo and confirm CI

**Files:** none (read-only)

- [ ] **Step 1:** Choose the first repo (TeacherHelper is a good first: workflow name `CI`, jobs `Backend (ruff + pytest)` and frontend lint/build).
- [ ] **Step 2:** Open GitHub → repo → **Actions**. Confirm a workflow runs on pull requests and can go green.
- [ ] **Step 3:** If there is no PR CI, stop. Add CI before any other part. No CI = no auto-merge, ever.

---

### Task 2: Create the Control Room project (once)

- [ ] **Step 1:** GitHub profile (or org) → **Projects** → **New project**.
- [ ] **Step 2:** Start from scratch → **Board**. Name: `Control Room`. Create project.
- [ ] **Step 3:** `⋯` (top right) → **Settings**.
- [ ] **Step 4:** **Manage access** → add every repo that will have issues on this board.
- [ ] **Step 5:** **Fields** → **Status** → rename/add options exactly: `Inbox`, `Ready`, `Doing`, `Blocked`, `Done`. Save.
- [ ] **Step 6:** **Fields** → **New field** → name `Priority` → **Single select** → options `P0`, `P1`, `P2` → Save.
- [ ] **Step 7:** **Fields** → **New field** → name `Iteration` → **Iteration** → duration `1` **weeks** → Save.
- [ ] **Step 8:** **Do not** duplicate **Auto-add to project** for each repo. GitHub Free = 1 of those workflows (you already have Langy: `is:issue,pr is:open`). Leave it or delete it; ingest for every other repo is Task 2b (`actions/add-to-project`).
- [ ] **Step 9:** `⋯` → **Workflows** → **Item added to project** → set **Status** to `Inbox` → enable.
- [ ] **Step 10:** Views: keep **Board** (columns = Status). Add **New view** → Table → rename `Sprint` → show Priority + Iteration → sort by Priority → **Save**. Add one view per repo: filter `repo:OWNER/REPO` → **Save**.

---

### Task 2b: Add issues via Action (replaces extra Auto-add)

Built-in Auto-add cannot scale. Use [actions/add-to-project](https://github.com/actions/add-to-project) in **each** repo.

- [ ] **Step 1:** GitHub → Settings → **Developer settings** → **Personal access tokens** → fine-grained (or classic with `project` + `repo`). Enable **Projects: Read and write** for the Control Room owner. Name: `add-to-control-room`. Copy once. Not in git.
- [ ] **Step 2:** Each repo → **Settings** → **Secrets** → **Actions** → `ADD_TO_PROJECT_PAT` = that token.
- [ ] **Step 3:** Copy the project URL from the browser (user project: `https://github.com/users/<you>/projects/<N>`).
- [ ] **Step 4:** Add `.github/workflows/add-to-control-room.yml`:

```yaml
name: Add to Control Room

on:
  issues:
    types: [opened, transferred]

jobs:
  add:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/add-to-project@v1.0.2
        with:
          project-url: https://github.com/users/REPLACE_ME/projects/REPLACE_ME
          github-token: ${{ secrets.ADD_TO_PROJECT_PAT }}
```

Pin the action version to a current release tag from that repo. Filter is issues-only (no PRs), which matches the spec better than Langy’s `is:issue,pr`.

- [ ] **Step 5:** Optional: delete the Langy built-in Auto-add and use this Action there too, so every repo behaves the same.

---

### Task 3: Labels and issue template (per repo)

**Files:**
- Create: `.github/ISSUE_TEMPLATE/control-room.yml`
- Create labels in GitHub UI

- [ ] **Step 1:** Repo → **Issues** → **Labels** → New label (one each):

| Name | Color (suggested) |
|---|---|
| `ready` | `#0E8A16` |
| `audit` | `#5319E7` |
| `test` | `#1D76DB` |
| `integrate` | `#006B75` |
| `implement` | `#0052CC` |
| `realize` | `#0052CC` |
| `blocked` | `#B60205` |

- [ ] **Step 2:** Add the template (commit on a branch or `main` as you prefer):

```yaml
name: Control room task
description: Agent-ready card (GWT + verify). Label ready to start a Cloud Agent.
title: "[type] "
labels: []
body:
  - type: dropdown
    id: job_type
    attributes:
      label: Job type
      options:
        - implement
        - realize
        - test
        - integrate
        - audit
    validations:
      required: true
  - type: textarea
    id: gwt
    attributes:
      label: Given / When / Then
      description: Tests must fail without the change (except audit).
      placeholder: |
        Given ...
        When ...
        Then ...
    validations:
      required: true
  - type: textarea
    id: verify
    attributes:
      label: How to verify
      placeholder: Commands, pages, or report location (audit).
    validations:
      required: true
  - type: textarea
    id: notes
    attributes:
      label: Extra context
      required: false
```

- [ ] **Step 3:** Also add the matching type label when you file the issue (`implement`, `audit`, …).

---

### Task 4: AGENTS.md Done gate (per repo)

**Files:**
- Modify: `AGENTS.md` (append if missing)

- [ ] **Step 1:** Ensure `AGENTS.md` at repo root includes **Build & test** commands and this block:

```markdown
## Done gate

A non-audit change may merge only when:
- Tests cover the issue Given/When/Then (would fail without the change)
- CI is green
- PR body states what changed, why, and how to verify
- If API, config, or user-facing behavior changed: update docs/ or add an ADR

audit: report on the issue only. Do not merge.

After a successful deploy: short English checklist + Render/Vercel log links.
```

---

### Task 5: Branch protection and auto-merge (per repo)

- [ ] **Step 1:** Repo → **Settings** → **General** → **Pull Requests** → enable **Allow auto-merge**. Save.
- [ ] **Step 2:** **Settings** → **Rules** → **Rulesets** → **New ruleset** → **New branch ruleset** (or **Settings** → **Branches** → **Add branch protection rule** if you still use classic).
- [ ] **Step 3:** Fill:

| Field | Value |
|---|---|
| Ruleset name | `main-control-room` |
| Enforcement | Active |
| Target branches | `main` (or default branch) |
| Restrict deletions | On |
| Block force pushes | On |
| Require a pull request before merging | On |
| Required approvals | **0** |
| Require review from Code Owners | **Off** |
| Require status checks to pass | On |
| Required checks | This repo’s real CI (TeacherHelper: `Backend (ruff + pytest)` and `Frontend (lint + build)`) |
| Require branches to be up to date | On (if offered) |

- [ ] **Step 4:** Confirm you did **not** enable “require approvals ≥ 1”. That blocks unattended C.

---

### Task 6: Cursor GitHub + API key

- [ ] **Step 1:** https://cursor.com/dashboard → **Integrations** → **GitHub** → connect / grant this repo (including private).
- [ ] **Step 2:** https://cursor.com/dashboard/api → **Create key**. Name e.g. `control-room`. Copy once. Do not paste into chat or git.
- [ ] **Step 3:** Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:
  - Name: `CURSOR_API_KEY`
  - Value: the key from step 2
- [ ] **Step 4:** Repeat the secret on each repo (same key is fine).

---

### Task 7: `cursor-triage.yml` (per repo)

**Files:**
- Create: `.github/workflows/cursor-triage.yml`

Uses Cloud Agents API **v1** (`POST https://api.cursor.com/v1/agents`). Re-read https://cursor.com/docs/cloud-agent/api/endpoints if this fails.

```yaml
name: Cursor Triage

on:
  issues:
    types: [labeled]

permissions:
  contents: read
  issues: write

jobs:
  dispatch:
    if: github.event.label.name == 'ready'
    runs-on: ubuntu-latest
    steps:
      - name: Launch Cursor Cloud Agent
        env:
          CURSOR_API_KEY: ${{ secrets.CURSOR_API_KEY }}
        run: |
          set -euo pipefail
          ISSUE_TITLE=$(jq -r .issue.title "$GITHUB_EVENT_PATH")
          ISSUE_BODY=$(jq -r '.issue.body // ""' "$GITHUB_EVENT_PATH")
          ISSUE_URL=$(jq -r .issue.html_url "$GITHUB_EVENT_PATH")
          ISSUE_LABELS=$(jq -r '[.issue.labels[].name] | join(", ")' "$GITHUB_EVENT_PATH")
          REPO_URL="https://github.com/${{ github.repository }}"

          PROMPT_TEXT=$(jq -n \
            --arg title "$ISSUE_TITLE" \
            --arg body "$ISSUE_BODY" \
            --arg url "$ISSUE_URL" \
            --arg labels "$ISSUE_LABELS" \
            "Work on this GitHub issue.\n\nTitle: \($title)\nLabels: \($labels)\n\n\($body)\n\nIssue: \($url)\n\nFollow this repository AGENTS.md (commands and Done gate).\n\nRules:\n- If labels or body include audit: write a report as an issue comment. Do not change main. Do not merge.\n- Otherwise: add or update tests so the issue Given/When/Then would fail without your change. Run the repo test/lint/build commands. A PR will be opened (autoCreatePR).\n- PR body must state what changed, why, and how to verify.\n- If API, config, or user-facing behavior changed: update docs/ or add an ADR.\n- When the Done gate is satisfied: enable GitHub auto-merge (gh pr merge --auto --squash). Do not merge if CI is red, tests omit the GWT, or required docs are missing.\n- If you cannot satisfy the Done gate: comment on the issue with why and stop. Do not retry in a loop.\n- Do not force-push to main.")

          jq -n \
            --arg text "$PROMPT_TEXT" \
            --arg repo "$REPO_URL" \
            '{
              prompt: { text: $text },
              repos: [{ url: $repo, startingRef: "main" }],
              autoCreatePR: true,
              skipReviewerRequest: true
            }' > payload.json

          curl --fail-with-body --request POST \
            --url https://api.cursor.com/v1/agents \
            -u "${CURSOR_API_KEY}:" \
            --header "Content-Type: application/json" \
            --data @payload.json
```

- [ ] **Step 1:** Commit this file on `main` (or merge a PR) so Actions can run.
- [ ] **Step 2:** Do **not** put the API key in the YAML.

---

### Task 8: Optional merge-comment checklist (per repo)

**Files:**
- Create: `.github/workflows/control-room-merged.yml`

```yaml
name: Control room merged ping

on:
  pull_request:
    types: [closed]

permissions:
  pull-requests: write
  issues: write

jobs:
  checklist:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    steps:
      - name: Comment English checklist
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh pr comment "${{ github.event.pull_request.number }}" --body "$(cat <<'EOF'
          ## Deploy checklist (English)

          Production deploys from `main` (Vercel frontend, Render API).

          - [ ] Open the PR summary: what changed and how to verify
          - [ ] Vercel deploy succeeded (project dashboard → Deployments)
          - [ ] Render deploy succeeded (service → Logs / Events)
          - [ ] Smoke-test the production URLs
          - [ ] If deploy failed: move the issue to Blocked; consider revert

          Linked issue: check Development / closes #N on this PR.
          EOF
          )"
```

---

### Task 9: Slack (once)

- [ ] **Step 1:** https://cursor.com/dashboard → **Integrations** → **Slack** → **Connect**. Install the Cursor app. Finish: GitHub connected, default repo, usage-based pricing if asked.
- [ ] **Step 2:** Create public channels e.g. `#th` (TeacherHelper), later `#<repo>`. Channel settings only apply to **public** channels.
- [ ] **Step 3:** In each channel: `@Cursor settings` → set **default repository** to that channel’s repo.
- [ ] **Step 4:** Test: `@Cursor list my agents`.
- [ ] **Step 5:** Slack App Directory → **GitHub** → add to workspace. In the channel: `/github subscribe OWNER/REPO`.
- [ ] **Step 6:** Optional routing: Cursor Dashboard → **Cloud Agents** → **Routing Rules** → keyword `teacherhelper` → that repo.

Phone start without the Action: `@Cursor implement issue #12 in OWNER/REPO` (or rely on channel default).

---

### Task 10: Smoke test (one repo) before rolling out

- [ ] **Step 1:** File a throwaway issue with the Control room template, type `implement`, tiny GWT. Add label `ready`.
- [ ] **Step 2:** **Actions** tab → `Cursor Triage` green. https://cursor.com/agents or Slack `@Cursor list my agents` shows a run.
- [ ] **Step 3:** A PR opens. CI runs.
- [ ] **Step 4:** If you push a failing test on that branch (or the agent’s tests fail): PR must **not** merge. Issue → `Blocked` + comment.
- [ ] **Step 5:** Green Done-gate PR: auto-merge → `main` → Vercel/Render. Slack/GitHub show PR + the English checklist comment.
- [ ] **Step 6:** File an `audit` issue, label `ready`. Confirm **no** merge to `main`.
- [ ] **Step 7:** A Blocked issue must **not** start again until you remove `blocked` and add `ready`.

Only then repeat Tasks 2b + 3–8 on the next repo (~15–20 minutes). Do not duplicate built-in Auto-add.

---

### Task 11: Daily / gym loop (no more setup)

1. File issue (template) on the correct repo → lands in **Inbox**.
2. Set Priority + Iteration. When you want work: label **`ready`**.
3. Away: GitHub mobile (label) or Slack `@Cursor`.
4. Wait. If Blocked: talk in Slack/Cursor, fix the issue body, label `ready` again.
5. After merge: English checklist + logs; smoke-test prod if you want.

---

## Out of this plan (spec v1)

Standups, `#board-meeting` bots, GitHub Projects MCP, Telegram, Linear, Hermes.
