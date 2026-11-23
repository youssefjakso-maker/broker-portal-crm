---
name: Broker Portal Development Workflow
description: Use for any development, bugfix, UI, test, data-import, or review task in the Broker Portal CRM (Python/Flask/Jinja2/SQLite). Routes work through planning, design, implementation, testing, browser verification, and evidence-based review, while enforcing the project's safety rules (no .venv changes, no workbook edits, no production database, no unapproved schema changes).
---

# Broker Portal Development Workflow

This is the operating procedure for the Broker Portal CRM. It is an
orchestrator: load the specialist skills named in each stage instead of
repeating their instructions here.

## Project facts

- Project root: `C:\Users\Jakso\Downloads\Broker_Portal_V18_Workflow_Update\Broker_Portal_Final`
- Stack: Python 3.10+, Flask, Jinja2, SQLite, openpyxl, waitress, vanilla HTML/CSS/JavaScript.
- Not React, Next.js, Tailwind, Supabase, or a Node build pipeline.
- Source workbook: `data/projects Upated9-11 (1).xlsx` (read-only; never edit it).
- Data directory: `<project>/data`, overridable with `BROKER_PORTAL_DATA`.
- Startup: `run_portal.bat` (creates/updates `.venv`, installs dependencies, starts waitress).
- Tests: `tests/` with pytest; they must run against a temporary data directory.
- There is no git repository in this project. Do not assume `git diff`, branches, commits, or worktrees exist.

## Non-negotiable guardrails

1. Never modify, delete, recreate, or upgrade the existing `.venv` unless the user explicitly asks.
2. Never edit, rename, move, or regenerate the source workbook or customer/unit data.
3. Never create or migrate a production database. Use a temporary directory via `BROKER_PORTAL_DATA` for tests and verification.
4. Never change `.session_secret`, authentication defaults, CSRF behavior, or the database schema without explicit approval.
5. Back up every file before a destructive or broad edit, and list every changed/created file in the final report.
6. Keep existing UI and behavior unchanged unless the task is explicitly a UI/UX change.
7. Do not start Phase 0 or Phase 1 work, or any previously paused stage, without explicit approval.
8. Do not add frameworks, package managers, or build tooling that the project does not already use.
9. If a request conflicts with these rules, stop and ask before acting.

## Stage 1 — Planning (always)

1. Restate the goal, the scope, and what is explicitly out of scope.
2. Read the relevant code before proposing changes: routes, helpers, templates, static files, schema, and tests. Use `read`, `grep`, and `glob`; do not guess.
3. Identify the affected files, database tables, templates, tests, and data paths.
4. For multi-step or risky work, write a short plan with exact files and exact verification commands. Wait for approval before broad refactors, schema changes, data migrations, or destructive operations.
5. If requirements are ambiguous, ask one focused question. Do not invent data semantics (unit types, price rules, link remapping, timezone storage, or "Best Match" behavior).

## Stage 2 — Design (UI/UX work only)

- Load the `impeccable` skill before changing any template, CSS, layout, form, dashboard, or navigation.
- Treat the CRM as Impeccable's **Operate** mode: scanability, consistency, native expectations, and the real usage scene outrank decorative expression.
- Read the existing templates and CSS first; reuse the current tokens, spacing, components, and Jinja patterns.
- Preserve the existing visual system unless the user explicitly asks for a redesign.
- Do not introduce landing-page patterns, WebGL, shader effects, heavy animation, or a new design system into the CRM.

## Stage 3 — Implementation

- Follow the existing Flask/Jinja/SQLite patterns and naming.
- Keep the diff minimal and focused; do not edit unrelated code.
- Preserve authentication, authorization, CSRF, session, upload, and import behavior.
- Do not change the database schema as a side effect. If a schema change is unavoidable, stop and ask first.
- Add comments only where they explain a non-obvious decision.
- Keep the original workbook and the user's data untouched.

## Stage 4 — Testing

- Add or extend pytest tests under `tests/` for every behavior change.
- Tests must set `BROKER_PORTAL_DATA` to a temporary directory before importing `app.py`, and must never open or create `<project>/data/broker_portal.db`.
- Run the full suite, not only the new test:
  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests
  ```
  If the existing `.venv` is intentionally off-limits, use the approved development environment and say which one you used.
- For a reported bug or unexpected failure, load `systematic-debugging` before proposing a fix. Find the root cause first.
- Record the exact command, exit code, pass/fail counts, and warnings. Never claim a pass without fresh output.

## Stage 5 — Browser verification (when UI or HTTP behavior changed)

- Start the app on a spare port with an isolated data directory, for example:
  ```powershell
  $env:BROKER_PORTAL_DATA = Join-Path $env:TEMP ("bp_verify_" + [guid]::NewGuid())
  $env:PORT = "5099"
  .\run_portal.bat
  ```
- Load the built-in `browser` skill, then use the native browser tools: open the page, take a snapshot, exercise the changed flow, check console errors and failed network requests, and take a screenshot when the visual result matters.
- Verify the changed flow and at least one existing regression path (login, dashboard, projects, or the affected page).
- Stop the server and remove the temporary data directory when finished.
- If the browser is unavailable, say so explicitly and fall back to HTTP checks; never pretend a visual check happened.

## Stage 6 — Review and report

- Load `verification-before-completion` before making any completion claim.
- Re-read the changed files and check for unintended edits, leftover debug code, and missing tests.
- If any workbook/import work occurred, verify the workbook SHA-256 against the pre-change value.
- Report, in this order:
  1. What changed and why.
  2. Every modified and created file.
  3. Exact test and browser-verification results, including failures and warnings.
  4. Risks, limitations, and anything not verified.
  5. Rollback steps.
- Stop at the agreed boundary and wait for approval before starting the next phase.

## Skill routing

| Need | Skill |
|---|---|
| Orchestration and project guardrails | this skill (`broker-portal-workflow`) |
| UI/UX design, critique, audit, polish | `impeccable` |
| Bug, test failure, or unexpected behavior | `systematic-debugging` |
| Before claiming completion or success | `verification-before-completion` |
| Browser verification | built-in `browser` |
| OpenCode configuration questions | built-in `opencode` |

## Output contract

Keep reports concise and evidence-based. Prefer a short table of changed files,
the exact commands run, and the exact results. State failures honestly. Do not
describe a skill as "used" unless its instructions were actually loaded and
followed.
