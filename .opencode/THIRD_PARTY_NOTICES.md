# Third-Party Skill Notices

This project vendors the following third-party skills under `.opencode/skills/`.
They are development-time agent instructions; they are not imported by the
Flask application and do not change runtime behavior.

## Impeccable

- Source: https://github.com/pbakaus/impeccable
- Version: 4.10.0 (SKILL.md frontmatter)
- Commit installed: `b49177d32788f2dc585c42831d845dacf1ebed2c` (2026-11-18)
- License: Apache License 2.0 (see `.opencode/skills/impeccable/LICENSE`)
- Installed path: `.opencode/skills/impeccable/`
- Install method: official OpenCode manual copy from the repository's
  `.opencode/skills/impeccable/` directory, plus the project command at
  `.opencode/commands/impeccable.md`.

## Superpowers (selected skills)

- Source: https://github.com/obra/superpowers
- Version: v7.0.2
- Commit installed: `22f0b463e7a5e579904dd6211a520321035526f7` (2026-11-03)
- License: MIT (see `LICENSE` inside each installed skill folder)
- Installed skills:
  - `.opencode/skills/systematic-debugging/`
  - `.opencode/skills/verification-before-completion/`
- Install method: the two skills were copied as standard Agent Skills
  (`SKILL.md` plus their supporting files). The full Superpowers plugin was not
  installed because it requires git for its official OpenCode plugin install,
  injects a session-wide bootstrap, and assumes git worktrees, commits, and
  subagent review loops that this project does not use.

## Not installed

- `Leonxlnx/taste-skill` (tasteskill 2.5.1) — marketing/landing-page skill that
  requires Node 22+ for its gate scripts and is not appropriate for an internal
  CRM.
- `anthropics/skills` → `frontend-design` — superseded for this project by
  Impeccable, which is derived from it and adds OpenCode-native, app-focused
  workflows.
- `anthropics/skills` → `webapp-testing` — overlaps with OpenCode's built-in
  browser tools and requires a Playwright installation and browser binaries.
- `obra/superpowers` full plugin — see above.
