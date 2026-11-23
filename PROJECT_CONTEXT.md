# Broker Portal CRM — Project Context

**Last updated:** 2026-11-21
**OpenCode:** 2.3.2 (desktop) · **App version:** release-candidate (office) — see OFFICE_SETUP.md
**Status:** Release candidate for office LAN deployment. Phases P0, P1.1–P1.7.2 complete. Tests: 147 passing.

---

## 1. Project overview

Broker Portal CRM is a **private, single-host real-estate brokerage workspace** for Admins and Brokers. It combines the company's Excel inventory with Admin-created projects/units and a broker CRM in one Flask application.

- **Host model:** one hosted instance on a private LAN/VPN; all users share one `data/broker_portal.db`. Do not run separate copies per broker.
- **Not multi-tenant / not public-internet.** No HTTPS by default; set `BROKER_PORTAL_HTTPS=1` only behind HTTPS.
- **Source workbook:** `data/projects Upated9-11 (1).xlsx` — a convenience copy; it is **not** imported automatically. Upload via Data Management.

## 2. Current architecture

Single-file Flask app (`app.py`, ~2313 lines) plus Jinja2 templates and one CSS file. No frontend build pipeline.

- **Backend:** Python 3.10+ (dev machine has 3.14.10), Flask 3.x, Werkzeug, openpyxl, waitress, tzdata.
- **Frontend:** Jinja2 templates (`templates/*.html`), vanilla JS, single `static/style.css`.
- **Database:** SQLite (`data/broker_portal.db`), WAL-friendly single file, foreign keys ON.
- **Data dir resolution:** `_resolve_data_dir()` honors `BROKER_PORTAL_DATA` (used for test isolation); otherwise `<project>/data`.
- **Session secret:** `data/.session_secret` (generated on first run, mode 0600); override via `BROKER_PORTAL_SECRET`.
- **Startup:** `run_portal.bat` (locates Python 3.10+, creates `.venv`, pip installs, checks tzdata, starts app on `BROKER_PORTAL_HOST` (default 127.0.0.1) / `PORT` (default 5000)).
- **Templates (16):** admin, ai_project_import, audit, base, change_password, clients, client_detail, dashboard, listing, listing_edit, login, manual_project_detail, projects, project_detail, project_form, update_intelligence, version.
- **No git repository** in this project. Changes are tracked via backups + manifests, not `git diff`.

## 3. Database structure

Tables (from `init_db()` and migrations):

| Table | Purpose |
|---|---|
| `users` | Admin/broker accounts; `must_change_password` |
| `versions` | Excel import versions (draft/live/archived) with counts |
| `manual_projects` | Admin-created projects (independent of Excel) |
| `listings` | Units (Excel-sourced + manual), with override JSON + normalized filter fields |
| `clients` | CRM clients, ownership (`broker_id`/`assigned_to`/`created_by`), qualification, follow-up |
| `opportunities` | Client–listing opportunities |
| `activities` | Timeline entries per client |
| `favorites` | User↔listing favorites |
| `audit_logs` | Admin audit trail |
| `update_intelligence` | Stored AI/analysis summaries |

Key relationships: `listings.version_id → versions`, `listings.manual_project_id → manual_projects`; `clients.assigned_to/created_by → users`; `opportunities.client_id → clients (CASCADE)`, `listing_id → listings`; `activities.client_id → clients (CASCADE)`.

Schema is migrated idempotently in `init_db()` (ALTER TABLE adds missing columns; `_rebuild_listings_for_manual_inventory` rebuilds `listings` when manual-inventory columns are missing). **No schema change is allowed without explicit approval.**

## 4. Existing features

- **Inventory & projects:** Projects view grouping inventory by project; Excel `.xlsx/.xlsm` upload → draft validation → publish/archive/restore; original headers (incl. misspellings) retained; Admin manual projects/units; listing overrides with source vs. final values and history + per-field reset; manual units survive Excel republish.
- **Smart Match:** rule-based local recommendations (Best Match / Good Alternatives / Stretch Options) with reasons; preferred location dropdown from active Excel + active manual units; Sheikh Zayed vs New Zayed kept separate; budget flexibility Strict/Flexible/Very Flexible (80–160% etc.); space tolerance; wide total-price ranges handled via starting price (V17). Budget policy (revised 2026-11-19): exact/best = starting price <= stated budget; near-budget (alternative) = stated budget < price <= 110% of stated budget, clearly labeled "exceeds by X%"; excluded above 110%; lower window bound 60% of stated budget. Near-budget results are capped at "alternative" and sorted after exact matches. Missing price/location => no match; category/location conflict => hard exclusion.
- **CRM:** client qualification, lead source, temperature, preferred area/unit/size, budget flexibility, next action, follow-up date, notes, activity timeline, opportunities; broker sees only assigned clients; Admin sees all; Created By vs Assigned To; client transfer; dashboard follow-ups, notifications, global search, quick Add-to-Client, favorites, WhatsApp summaries, payment calculator.
- **Roles:** Admin (inventory, versions, manual projects/units, overrides, users, audit log); Broker (browse inventory, Smart Match, calculator, own clients/opportunities/activities/follow-ups). Server-side enforcement.
- **Security (V17):** CSRF on every POST form + fetch (400 without token); forced password change for default/reset accounts; login throttle 5 fails / (IP,email) / 15 min; HttpOnly/SameSite=Lax/12h session; security headers (CSP, X-Frame-Options, nosniff, Referrer-Policy, no-store); demo creds removed from login page; host defaults to 127.0.0.1.

## 5. Completed improvements (Phase 0 — verified)

Verified 2026-11-19 via pytest (14/14 pass, 2 deprecation warnings) using `.venv` + `bp_testdeps` (tzdata) on `PYTHONPATH`:

- **P0.1** Timezone startup handling (`_load_timezone`, `CAIRO_TZ`, `cairo_now`, `display_dt` UTC→Cairo, `test_timezone`).
- **P0.4** Windows startup script (`run_portal.bat` with Python 3.10+ discovery, venv create/verify, dependency install, tzdata check).
- **P0.5** `BROKER_PORTAL_DATA` isolation (`_resolve_data_dir`, `DATA/UPLOADS/DB` resolution, `test_paths`).
- **Test scaffold:** `conftest.py` (temp data dir set before import, `sys.dont_write_bytecode`), `test_import_smoke`, `test_pages`, `test_paths`, `test_schema`, `test_security`, `test_timezone`.
- **Comprehensive release (2026-11-19):** client multi-location + property category + qualification fields; Smart Match multi-location/category; Luxury Editorial design system (tokens, dark sidebar, light workspace); `tests/test_client_locations.py`. See DEVELOPMENT_LOG Entry 0005.
- **P1.1 (2026-11-19):** price parser correction (deterministic unit resolution, malformed-suffix rejection); `tests/test_price_parser.py`. See Entry 0007.
- **P1.2 (2026-11-19):** listing identity preservation via `listing_uid`; publish re-points favorites/opportunities; `tests/test_listing_identity.py`. See Entry 0008.
- **P1.3 (2026-11-19):** restore validation (eligibility, serious errors, no-op, empty version, transaction safety, reference preservation); `tests/test_restore_validation.py`. See Entry 0009.
- **P1.4 (2026-11-19/20):** timezone handling — UTC storage convention, Cairo↔UTC conversion for follow-ups, consistent due/today/upcoming logic, cairo_input filter; `tests/test_timezone_handling.py`. See Entry 0010.
- **P1.5 (2026-11-20):** unit type normalization — separate property category from unit type; `canonical_unit_type` helper + `unit_type_canonical` column; Smart Match category/unit matching; `tests/test_unit_type_normalization.py`. See Entry 0011.
- **P1.5 correction (2026-11-20):** unknown unit types now unclassified (empty canonical/category); unknown preferences excluded; targeted idempotent backfill; see Entry 0012.
- **P1.6 (2026-11-20):** Smart Match improvements — exact/partial/near-budget/stretch groups separated, near-budget badge, missing-info reasons, empty state, sort priority; `tests/test_smart_match_comprehensive.py` (new, 8), `tests/test_smart_match_policy.py`, `tests/test_unit_type_normalization.py` updated. See Entry 0013 + 0014.
- **P1.6 corrections (2026-11-20):** lower budget boundary corrected to 60% (was 48%); missing required-data handling (space/bedrooms) prevents Best; genuine Partial/Stretch tests; browser verified. See Entry 0015.
- **P1.6 final UI cleanup (2026-11-20):** Stretch/Lower-Fit group removed; three groups only (Best Matches, Partial Matches, Near-Budget Alternatives); stretch reassigned to Partial. See Entry 0016.
- **P1.7 audit tasks 1–3 (2026-11-20):** timezone unification (dashboard/notifications/inject UTC + cairo_day_utc_bounds); input validation (edit_client, update_client_status, users); dashboard sales target env (BROKER_PORTAL_SALES_TARGET) + robust _money. See Entry 0017.
- **P1.7 audit task 4 (2026-11-20):** tests/test_rbac.py (9), tests/test_input_validation.py (7); `opencode/beam-free`.
- **P1.6 verification (2026-11-20):** empty-state root cause documented (correct); deterministic A-I dataset verified; 4 groups verified; browser evidence collected; 84/0. See Entry 0014.
- **Legacy follow-up note:** Pre-convention follow-up values may be Cairo-local naive timestamps. They are preserved as-is and cannot be distinguished from UTC values; display may be off for legacy rows. New/edited follow-ups follow the UTC convention.

Counts: 14 passing tests, 3 modified existing files (app.py, run_portal.bat, pytest.ini), 9 new files (conftest + 6 test modules + requirements-dev.txt + this context is later). No production DB created; workbook SHA-256 unchanged.

## 6. Known bugs / limitations

- `.venv` tzdata **resolved 2026-11-19**: `tzdata==2026.6` installed (backup at `Broker_Portal_Backups/Broker_Portal_Venv_PreTzdata_20261119_212746/`). `run_portal.bat` step 5 now passes. No other package changed. **Do not recreate `.venv` without approval.**
- `datetime.utcnow()` deprecation warnings in app.py (admin user seeding) — `datetime.utcnow()` was deprecated in Python 3.12 (not removed in 3.13). Cosmetic; tracked as technical debt. Not a failure.
- No git repository → no `git diff`; use file manifests + hashes for change tracking.
- Login throttle is in-memory (`_LOGIN_FAILS`) and resets on restart.
- Payment calculator is indicative only.
- Wide price ranges: handled via starting price (V17); exact-unit confirmation still needed for wide ranges.

## 7. Pending development phases

- **Phase 1 — Pending approval (do not start without user approval):**
  - P1.1 Price parser correction
  - P1.2 Listing identity preservation
  - P1.3 Restore validation
  - P1.4 Timezone handling
  - P1.5 Unit type normalization
  - P1.6 Smart Match improvements
- No Phase 0/1 re-execution without explicit approval.

## 8. Technical decisions and reasons

- Single-file Flask app (legacy) retained to avoid a large refactor; new features added in-place.
- SQLite chosen for local internal use; no ORM.
- `BROKER_PORTAL_DATA` env var for test isolation (must be set before `app.py` import because `DATA/DB` resolve at import time).
- Controlled area labels (Sheikh Zayed ≠ New Zayed) enforced in normalization and matching.
- `RES` unit category kept distinct from `Apartment`.
- CSRF auto-injected into rendered POST forms via `security_headers`.
- Smart Match uses starting price for wide ranges (V17) to avoid hiding affordable projects behind huge ranges.
- Session secret persisted to `data/.session_secret` so restarts keep sessions valid.

## 9. Testing procedures

- **Never** use real customer data or the production DB in tests.
- Set `BROKER_PORTAL_DATA` to a temp dir **before** importing `app.py` (conftest does this).
- Run: `.\.venv\Scripts\python.exe -m pytest tests` (`pytest` is not in `.venv`; use `PYTHONPATH` pointing at a pytest install, e.g. `bp_testdeps`. `tzdata` is now in `.venv` since 2026-11-19).
- Full suite must pass; report exact command, exit code, counts, warnings.
- Browser verification: start app on a spare port with isolated `BROKER_PORTAL_DATA`, use OpenCode browser skill, exercise changed flow + one regression path, then stop server and delete temp data.
- Workbook integrity: verify SHA-256 `3BBEC06F12CADFBDAA446E93D3ED0E11DCA552067564A15B4A07021540B0F59B` before/after any import work.

## 10. Important safety restrictions

1. Never modify, delete, recreate, or upgrade `.venv` without explicit approval.
2. Never edit, rename, move, or regenerate the source workbook or customer/unit data.
3. Never create or migrate a production database; use `BROKER_PORTAL_DATA` temp dirs.
4. Never change `.session_secret`, auth defaults, CSRF behavior, or DB schema without approval.
5. Back up before destructive/broad edits; list every changed/created file in the final report.
6. Keep existing UI/behavior unchanged unless the task is explicitly UI/UX.
7. Do not start Phase 0/1 or any paused stage without approval.
8. Do not add frameworks, package managers, or build tooling the project doesn't use.
9. If a request conflicts with these rules, stop and ask.
10. Treat `AGENTS.md` and `broker-portal-workflow` skill as the operating procedure.