# Broker Portal — Agent Instructions

This project is a Python/Flask/Jinja2/SQLite CRM. It is not React, Next.js, Tailwind, or Supabase.

Before any development, bugfix, UI, test, or review task, load the `broker-portal-workflow` skill and follow its stages.

- UI/UX work: also load `impeccable`.
- Bugs or test failures: also load `systematic-debugging`.
- Before claiming completion: load `verification-before-completion`.
- Browser checks: use the built-in `browser` skill when it is available.

Never modify or recreate `.venv`, edit `data/projects Upated9-11 (1).xlsx`, change `.session_secret`, or create/migrate a production database. Tests must use `BROKER_PORTAL_DATA` with a temporary directory. Phase 0/1 work requires explicit approval.
