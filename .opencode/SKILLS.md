# Installed Agent Skills

These skills are project-scoped and live under `.opencode/skills/`. OpenCode
discovers them automatically when the Broker Portal project is the active
workspace.

## Installed

| ID | Purpose | Source |
|---|---|---|
| `broker-portal-workflow` | Project-specific workflow: planning, design routing, implementation, testing, browser verification, review, and safety guardrails. | This project |
| `impeccable` | UI/UX design, critique, audit, polish, and design-system guidance for app/admin interfaces. | https://github.com/pbakaus/impeccable (Apache-2.0) |
| `systematic-debugging` | Root-cause investigation before proposing fixes. | https://github.com/obra/superpowers (MIT) |
| `verification-before-completion` | Requires fresh command output before claiming work is complete. | https://github.com/obra/superpowers (MIT) |

## Invocation

- Load the workflow first for any development task: `skill({ id: "broker-portal-workflow" })`.
- Load UI guidance before changing templates/CSS: `skill({ id: "impeccable" })`.
- Load debugging guidance for bugs/test failures: `skill({ id: "systematic-debugging" })`.
- Load the completion gate before reporting success: `skill({ id: "verification-before-completion" })`.
- Use the built-in browser tools for browser verification (load the `browser` skill first).
- The project command `/impeccable <target>` is available from `.opencode/commands/impeccable.md`.

## Verification

Verified on 2026-11-19 against OpenCode 2.3.2 with a standalone server rooted at
this project:

- `GET /api/skill?sessionID=...` after location config load returned
  `broker-portal-workflow`, `impeccable`, `systematic-debugging`, and
  `verification-before-completion` alongside the built-in skills.
- `POST /api/experimental/session/{id}/skill` with `resume: false` returned
  HTTP 204 for all four skills and appended four `type: "skill"` messages with
  their full instruction text.
- `GET /api/command?sessionID=...` listed `impeccable`.
- Impeccable's launcher downloaded and ran engine 0.1.27 without Node
  (`impeccable context` exit code 0).

## Scope

The full Superpowers plugin, Taste Skill, Anthropic `frontend-design`, and
Anthropic `webapp-testing` were audited but not installed. See
`THIRD_PARTY_NOTICES.md` for the reasons.
