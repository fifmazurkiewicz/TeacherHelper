---
name: mutation-testing
description: Use when the user asks for mutation testing or how well tests catch bugs, or to offer it for high-risk code after behavioral-tests; always ask before running.
---

# Mutation Testing

Mutation testing makes small deliberate changes to the code, called mutants,
and reruns the tests. A killed mutant fails a test; a surviving mutant is a
regression the tests miss. It is slow and may need a new development
dependency, so it is optional and runs only with the user's approval.

## Ask first

Never run mutation testing or add its tooling without explicit approval for
this run. Propose the scope (changed or high-risk files only, never the whole
repository by default), the tool, any dependency or configuration it needs,
and the expected cost in time; then ask. If the user declines, stop and note
that mutation testing was offered and declined.

## Choose the tool

Prefer a tool and configuration the project already has.

- **Python with pytest:** `mutmut`, added as a development dependency with the
  project's package manager, for example `uv add --dev mutmut`. Set the paths
  to mutate in its `pyproject.toml` configuration as the installed version
  documents, run `mutmut run`, list results with `mutmut results`, and inspect
  a survivor with `mutmut show <mutant>`. Use `cosmic-ray` only when the
  project already uses it or needs distributed runs.
- **TypeScript or JavaScript with Vitest or Jest:** StrykerJS, added as
  development dependencies `@stryker-mutator/core` and the matching runner,
  such as `@stryker-mutator/vitest-runner`. Run `npx stryker run --mutate
  <files>`, with `--incremental` for repeated runs.

Adding a dependency or configuration is a project change covered by the same
approval; keep it in the repository only if the user wants it. Never install
global tools.

## Run and triage

1. Confirm the relevant test suite passes; mutation results on a failing suite
   are meaningless.
2. Run the tool on the approved scope only.
3. Triage each surviving mutant:
   - **Equivalent:** the change cannot alter observable behavior. Record it
     and move on.
   - **Gap:** strengthen or add a behavioral test with the `behavioral-tests`
     skill, asserting the observable outcome the mutant breaks. Never write a
     test that checks the mutated code's shape.
   - **Accepted:** a low-risk gap the user chooses to leave, with the reason.
4. Rerun the affected scope after adding tests.

Do not chase a perfect score or kill mutants with tests of implementation
details.

## Report

State the tool, scope, killed and total mutants, runtime, and a table of
surviving mutants with location, change, and verdict (gap fixed, equivalent,
or accepted). Add it to the regression summary and to `evidence.md` when a
change-context folder exists.
