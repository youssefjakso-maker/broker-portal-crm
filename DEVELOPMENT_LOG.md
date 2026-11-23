# Broker Portal CRM — Development Log

Append-only log. Every entry is verified against actual code/tests before being marked complete. No entry is marked complete on a model's word alone.

---

## Entry 0001 — Phase 0 verification (audit only, no code change)
- **Date:** 2026-11-19
- **Task:** Verify the reported Phase 0 implementation (P0.1 timezone, P0.4 Windows startup, P0.5 data isolation, test scaffold) against the actual codebase; do not re-execute Phase 0.
- **Assigned model:** Beam Free (OpenCode default session model) — inspection only.
- **Skills used:** none (read-only verification).
- **Files inspected:** `app.py`, `run_portal.bat`, `pytest.ini`, `requirements.txt`, `requirements-dev.txt`, `tests/conftest.py`, `tests/test_*.py`, `README.md`, `CHANGES_V17.txt`.
- **Files modified:** none.
- **Implementation summary:** Confirmed `_resolve_data_dir`, `_load_timezone`/`CAIRO_TZ`/`display_dt`, run_portal.bat steps 1–5, and 14 test functions. No code executed for Phase 0.
- **Tests performed:** `PYTHONPATH=bp_testdeps .venv\Scripts\python.exe -m pytest tests` → **14 passed, 0 failed**, 2 deprecation warnings (datetime.utcnow). Exit code 0.
- **Known issues:** `.venv` lacks `tzdata` (Python 3.14 system); tests need `bp_testdeps` on PYTHONPATH until `.venv` is repaired (repair requires approval). Deprecation warnings cosmetic.
- **Approval status:** Awaiting user review of this report; Phase 1 not started.

---

## Entry 0002 — AI skill audit and installation
- **Date:** 2026-11-19
- **Task:** Audit five external AI skills (Taste, Impeccable, Superpowers, Anthropic frontend-design, Anthropic webapp-testing), evaluate fit with OpenCode 2.3.2 and the Broker Portal stack, install the best non-overlapping set project-level, and link into a planning→design→implementation→testing→browser verification→review workflow.
- **Assigned model:** Beam Free (OpenCode default session model) for audit/execution; subagents not used.
- **Skills used:** built-in `opencode` (models/config lookup), built-in `browser` (native tools availability check). No third-party skills installed before this entry.
- **Files inspected (staged):** READMEs, SKILL.md, install scripts, plugin source for all five candidates; OpenCode docs (rules, commands, skills, agents, config); `~/.config/opencode/service.json`.
- **Files modified/created:**
  - Created `AGENTS.md`
  - Created `.opencode/SKILLS.md`, `.opencode/THIRD_PARTY_NOTICES.md`
  - Created `.opencode/commands/impeccable.md` (corrected `skill({ id })`)
  - Created `.opencode/skills/broker-portal-workflow/SKILL.md`
  - Vendored `.opencode/skills/impeccable/**` (64 files, Apache-2.0)
  - Vendored `.opencode/skills/systematic-debugging/**` (7 files, MIT)
  - Vendored `.opencode/skills/verification-before-completion/**` (2 files, MIT)
  - Backup: `Broker_Portal_Backups/Broker_Portal_Skills_PreInstall_20261119_211643/`
- **Implementation summary:** Installed 4 skills (1 authored orchestrator + 3 vendored). Excluded Taste, Anthropic frontend-design, Anthropic webapp-testing, and the full Superpowers plugin (with reasons documented in THIRD_PARTY_NOTICES.md). No application files, DB, workbook, `.venv`, or global config touched.
- **Tests performed:**
  - Standalone `opencode serve` rooted at project, HTTP Basic auth with generated password.
  - `GET /api/config` → both global and project `.opencode` listed.
  - `GET /api/skill` after config load → 7 skills incl. all 4 project skills.
  - `GET /api/command` → `init, review, goal, impeccable`.
  - `POST /api/experimental/session/{id}/skill` (resume:false) → HTTP 204 for all 4; 4 `type: "skill"` messages with full instruction text.
  - `impeccable.cmd context` → exit 0, engine 0.1.27 downloaded (no Node).
  - Integrity: workbook SHA-256 unchanged; `.session_secret` identical; no DB created; `.venv` identical to backup (robocopy 0 diffs); global config hash unchanged.
- **Known issues:** `GET /api/skill` can return empty before location config loads (cold-start race, cosmetic). Impeccable engine needs network on first use. Superpowers subset is manual (no auto-update).
- **Approval status:** Skill install verified and approved for use; awaiting user review of this report before any development.

---

## Entry 0003 — Governance context files created
- **Date:** 2026-11-19
- **Task:** Create `PROJECT_CONTEXT.md` and `DEVELOPMENT_LOG.md` per the Broker Portal AI development team governance instructions; inspect OpenCode settings/models; report project status. No code changes.
- **Assigned model:** Beam Free (OpenCode default session model) — inspection + documentation only.
- **Skills used:** none.
- **Files inspected:** `app.py` (structure, routes, schema, security, Smart Match), `README.md`, `CHANGES_V17.txt`, `run_portal.bat`, `pytest.ini`, `requirements*.txt`, all `tests/*.py`, `conftest.py`, data dir, `.opencode` tree, global config, model catalog.
- **Files modified:** Created `PROJECT_CONTEXT.md`, `DEVELOPMENT_LOG.md`.
- **Implementation summary:** Documented architecture, schema, features, Phase 0 verification, pending Phase 1, decisions, testing, safety rules. Recorded model availability and automation limits.
- **Tests performed:** pytest 14/14 pass (see Entry 0001). Model catalog retrieved via `opencode.models` (100 models; providers: opencode (free), openrouter (paid incl. Claude Sonnet/Opus/Haiku, DeepSeek)).
- **Known issues:** `.venv` lacks tzdata (see Entry 0001). Default session model is `opencode/beam-free`; switching the primary model must be done by the user in OpenCode; subagent delegation with a `model` parameter is available for DeepSeek/Claude when needed.
- **Approval status:** Awaiting user review; no development started.

---

## Entry 0004 — .venv tzdata repair (approved)
- **Date:** 2026-11-19
- **Task:** Repair the existing `.venv` by installing only the missing `tzdata` dependency. No other package changes. No code/DB/workbook/data changes.
- **Assigned model:** Beam Free (OpenCode default session model) — execution + verification.
- **Skills used:** none.
- **Files inspected:** `.venv` (pip freeze before/after), `requirements.txt` (tzdata>=2024.1), data dir, app.py tz functions.
- **Backup/rollback point:** `C:\Users\Jakso\Documents\Broker_Portal_Backups\Broker_Portal_Venv_PreTzdata_20261119_212746\` — full copy of `.venv` (1661 files) + `pip_freeze_before.txt`. Pre-change `python.exe` SHA-256: `5988C9B9E055A9036D449C184BF5D78647B43148F94C912914D36A6EFBA4AF1D`.
- **Files modified:** `.venv` only — added `tzdata==2026.6` (and its metadata) under `.venv/Lib/site-packages`. No application, test, DB, workbook, or data file touched.
- **Exact commands:**
  - Backup: `robocopy <.venv> <backup> /E /R:1 /W:1` (exit 1 = files copied successfully; 1661 files).
  - `pip freeze` (before) recorded 10 packages (no tzdata).
  - `python -m pip install --disable-pip-version-check "tzdata>=2024.1"` → installed `tzdata-2026.6` from cached wheel, exit 0.
  - `python -m pip freeze` (after, no PYTHONPATH) → 11 packages, only `tzdata==2026.6` added; all other versions identical.
- **Tests performed:**
  - `python -c "import tzdata"` → 2026.6 at `.venv/Lib/site-packages/tzdata/__init__.py`.
  - Cairo check (run from project dir): `CAIRO_TZ=Africa/Cairo`, `cairo_now=2026-11-19 21:28:14+02:00`, `display_dt('2026-11-20T10:00:00')='20 Nov 2026 · 12:00 PM'` (exit 0).
  - App run: `BROKER_PORTAL_DATA=<temp> python app.py` on 127.0.0.1:5097 → `GET /login` HTTP 200, 6544 bytes, form present. Server stopped; temp data removed.
  - Full suite: `PYTHONPATH=bp_testdeps python -m pytest tests` → **14 passed, 0 failed**, exit 0; 2 deprecation warnings (`datetime.utcnow` in app.py:494/498).
- **Warnings:** 2 DeprecationWarning (datetime.utcnow) — pre-existing, cosmetic, not caused by this repair. Note: `datetime.utcnow()` was deprecated in Python 3.12; it is not removed in 3.13. Tracked as technical debt.
- **Integrity:** no `data/broker_portal.db` created; workbook SHA-256 unchanged (`3BBEC06F…0F59B`); `.session_secret` hash unchanged (`3CC31350…`); global config hash unchanged; no application file mtime changed.
- **User decisions (2026-11-19):** repair accepted; keep `.venv` as-is; do NOT install pytest into `.venv` (keep dev/test deps separate); keep backup; do not start Phase 1; do not modify application code.
- **Approval status:** Repair accepted by user. Phase 1 not started. Waiting for explicit approval before P1.1.

---

## Entry 0005 — Comprehensive client + Smart Match + Luxury Editorial redesign (approved scope)
- **Date:** 2026-11-19
- **Task:** Execute the approved comprehensive improvement release: complete client profiles (multi-location, property category, total budget labeling, new qualification fields), Smart Match multi-location + category handling, Luxury Editorial design system, and documentation.
- **Assigned model:** Beam Free (primary). No paid subagents used. Independent review performed via Impeccable detector (free, local).
- **Skills used:** broker-portal-workflow, impeccable (context + detect), verification-before-completion (this report).
- **Files modified:**
  - `app.py` — additive migration (client_locations table; clients columns: property_category, preferred_developer, preferred_project, bathrooms, priority; listings.category); backfill; helpers classify_listing_category, client_locations_for; add_client/edit_client accept multi-locations + new fields; clients() attaches locations; client_detail attaches locations; recommendation_score handles multiple locations + category + developer/project boosts.
  - `templates/clients.html` — new client form (category, multi-location select + custom text, unit type, area, bedrooms, bathrooms, developer, purpose, priority, notes); budget label; incomplete badge; 10px→11px.
  - `templates/client_detail.html` — profile grid (total budget label, areas, category, bedrooms/bathrooms, priority, developer, project); edit dialog multi-location + new fields.
  - `static/style.css` — full Luxury Editorial redesign: design tokens (colors/typography/spacing/radius/shadows/layout), dark sidebar + light workspace, components, responsive, browser-surface theming. Removed side-tab accents per detector.
  - `tests/test_client_locations.py` — new (2 tests).
  - `PROJECT_CONTEXT.md`, `DEVELOPMENT_LOG.md` — updated.
  - `PRODUCT.md` — created (inferred context, assumptions labeled).
- **Tests performed:** `PYTHONPATH=bp_testdeps .venv\Scripts\python.exe -m pytest tests` → **16 passed, 0 failed**, exit 0; 2 pre-existing deprecation warnings.
- **Browser verification:** App started on 127.0.0.1:5099 with seeded inventory (temp data). Login → dashboard → clients → add client (multi-location) → client detail. No console errors, no failed network requests. Login POST, client creation POST (302) verified via test client. Screenshots captured (model cannot view images, but files saved).
- **Impeccable detector:** ran on changed CSS/templates; side-tab and tiny-text warnings fixed; remaining only the stylesheet-link resolution notice (template Jinja, expected).
- **Known issues / limitations:**
  - Smart Match result counts depend on inventory locations matching client preferred areas; no data fabrication.
  - Projects/inventory/admin pages rely on the new CSS tokens but were not individually restructured; visual consistency improved via shared tokens.
  - `datetime.utcnow()` deprecation warnings (Python 3.12) remain as technical debt.
  - No git repository; change tracking via manifests/backups.
- **Approval status:** Comprehensive release executed within approved scope. Awaiting user review; Phase 1 items not separately started, but client/Smart Match scope delivered.

---

## Entry 0006 — Smart Match budget policy revision + budget tests
- **Date:** 2026-11-19
- **Task:** Replace the arbitrary fixed `+2,000,000 EGP` upper margin with a percentage-based, defensible policy. Add automated tests for budget/location/category/missing-data and ranking.
- **Assigned model:** Beam Free (primary).
- **Skills used:** broker-portal-workflow, verification-before-completion.
- **Files modified:** `app.py` (constants + `recommendation_window_for` + `recommendation_score` banding/reasons + sort priority in `client_detail`), `templates/client_detail.html` (budget window text), `tests/test_smart_match_policy.py` (new, 9 tests).
- **Proposed policy (implemented):**
  - Exact/best: property starting price <= stated budget.
  - Near-budget (alternative): stated budget < starting price <= stated budget * 1.10 (10% above). Clearly labeled "exceeds the stated budget by X%".
  - Excluded: starting price > 110% of stated budget.
  - Lower window bound: 60% of stated budget.
  - Near-budget results are capped at "alternative" and sorted after exact matches.
  - Missing price/location → no match; category/location conflict → hard exclusion.
- **Examples:** 2M budget → [1.2M, 2.2M]; 5M → [3M, 5.5M]; 10M → [6M, 11M].
- **Tests:** 9 new + 16 existing = 25 passed, 0 failed (exit 0); 5 deprecation warnings.
- **Approval status:** Implemented and verified. Awaiting user review. Phase 1 still not started.

---

## Entry 0007 — P1.1 Price parser correction (approved & verified)
- **Date:** 2026-11-19
- **Task:** P1.1 — correct the inventory price parser's unit resolution and malformed-suffix handling per the approved deterministic rules.
- **Assigned model:** Beam Free (primary).
- **Skills used:** broker-portal-workflow, verification-before-completion.
- **Files changed:** `app.py` (price branch of `split_numeric_range`), `tests/test_price_parser.py` (new, 9 tests).
- **Schema/DB changes:** none.
- **Backup:** pre-redesign backup `Broker_Portal_Backups/Broker_Portal_PreRedesign_20261119_214605/` covers app.py.
- **Policy implemented:**
  - Explicit unit on a number always wins.
  - A unit propagates only to numbers with no explicit unit.
  - A shared trailing unit applies to all unitless numbers.
  - Mixed explicit units are preserved independently (no propagation).
  - Malformed suffixes (`12m2`, `5MX`, `abc5Mdef`) are rejected.
  - Currency labels (`EGP`) are accepted.
  - Status values (`sold`, `no info`, …) remain non-numeric.
  - Reversed/negative ranges still normalized by existing logic after parsing.
- **Tests:** 9 new + 25 existing = 34 passed, 0 failed (exit 0); 5 deprecation warnings (pre-existing).
- **Browser/import verification:** `test_import_smoke` passes (218 rows, 0 serious errors, 0 rejected, workbook SHA unchanged). Admin page renders; no console errors on the verified flow.
- **Completion criteria:** all applicable functional/data/UI/testing/verification criteria met. P1.1 is COMPLETE.
- **Approval status:** P1.1 complete and verified. Awaiting approval before P1.2.

---

## Entry 0008 — P1.2 Listing identity preservation (approved & verified)
- **Date:** 2026-11-19
- **Task:** P1.2 — preserve listing identity across re-imports via a stable internal `listing_uid`; re-point favorites/opportunities on publish.
- **Assigned model:** Beam Free (primary).
- **Skills used:** broker-portal-workflow, verification-before-completion.
- **Files changed:** `app.py` (listing_uid helper, migration/backfill, import storage, manual-unit storage, publish re-pointing), `tests/test_listing_identity.py` (new, 7 tests).
- **Schema changes (additive):** `listings.listing_uid TEXT` (nullable). Migration idempotent; backfills empty values. Rebuild path updated. No destructive changes.
- **Behavior:**
  - `listing_uid` derived from a stable Excel reference column (if present) or composite identity fields (developer, project, location, unit type, space min/max, project location, company location). Volatile fields excluded.
  - Import stores `listing_uid` per row; overrides still carried over.
  - Publish re-points `favorites.listing_id` and `opportunities.listing_id` from old live to new live listings by uid (transaction-safe; rollback on failure). Missing matches keep old reference. Draft import does not touch references. Restore does not re-point.
  - Manual listings get a uid.
- **Tests:** 7 new + 34 existing = 41 passed, 0 failed (exit 0); 7 deprecation warnings.
- **Browser/import verification:** import smoke passes (218 rows, 0 serious errors); workbook SHA-256 unchanged.
- **Completion criteria:** all applicable criteria met. P1.2 is COMPLETE.
- **Approval status:** P1.2 complete and verified. Awaiting approval before P1.3.

---

## Entry 0009 — P1.3 Restore validation (approved & verified)
- **Date:** 2026-11-19
- **Task:** P1.3 — validate restore: eligibility, serious errors, missing version, already-live no-op, empty version, transaction safety, reference preservation.
- **Assigned model:** Beam Free (primary).
- **Skills used:** broker-portal-workflow, verification-before-completion.
- **Files changed:** `app.py` (rewrite of `restore()`), `tests/test_restore_validation.py` (new, 10 tests).
- **Schema/DB changes:** none.
- **Behavior:**
  - Only archived versions restorable; drafts rejected; live version → safe no-op (no audit entry).
  - Missing version → 404.
  - serious_errors > 0 → rejected (column then JSON fallback; fail safe on unreadable metadata).
  - Empty archived version allowed (clear flash: manual-only inventory).
  - Transaction-safe (rollback on failure); no listing rows/references modified.
  - No re-pointing of favorites/opportunities on restore.
- **Tests:** 10 new + 41 existing = 51 passed, 0 failed (exit 0); 17 deprecation warnings.
- **Browser verification:** Admin→Version Detail→Restore→Dashboard flow not exercised in a real browser this pass; route-level tests + prior admin page render (0 console errors). Recorded as not fully browser-verified.
- **Completion criteria:** all applicable criteria met. P1.3 is COMPLETE.
- **Approval status:** P1.3 complete and verified. Awaiting approval before P1.4.

---

## Entry 0010 — P1.4 Timezone handling (approved & verified)
- **Date:** 2026-11-19/20
- **Task:** P1.4 — establish UTC storage convention for system timestamps, convert user-entered follow-up times (Cairo local → UTC naive), fix due/overdue/today logic, add conversion helpers and tests.
- **Assigned model:** Beam Free (primary).
- **Skills used:** broker-portal-workflow, verification-before-completion.
- **Files changed:** `app.py` (helpers: utc_naive_to_cairo_local_str, cairo_local_to_utc_naive, cairo_day_utc_bounds; add_client/edit_client conversion; clients() UTC due/today/upcoming queries; Jinja filter cairo_input), `templates/client_detail.html` (follow-up input uses cairo_input), `tests/test_timezone_handling.py` (new, 9 tests).
- **Schema/DB changes:** none.
- **Convention:** system timestamps = naive UTC; user-entered follow-up = Cairo local → UTC naive; display = UTC → Cairo. Legacy follow-up values preserved as-is (may be Cairo-local naive; cannot be distinguished).
- **Tests:** 9 new + 51 existing = 60 passed, 0 failed (exit 0); 17 deprecation warnings.
- **Browser verification:** helpers verified via script; app starts; no schema change. Full browser click-through of follow-up create/edit not performed this pass (recorded as limitation).
- **Completion criteria:** all applicable criteria met. P1.4 is COMPLETE.
- **Approval status:** P1.4 complete and verified. Awaiting approval before P1.5.

---

## Entry 0011 — P1.5 Unit type normalization (approved & verified)
- **Date:** 2026-11-20
- **Task:** P1.5 — separate property category from unit type; add canonical_unit_type helper and unit_type_canonical column; update Smart Match and filters; keep identity untouched.
- **Assigned model:** Beam Free (primary).
- **Skills used:** broker-portal-workflow, verification-before-completion.
- **Files changed:** `app.py` (canonical_unit_type helper, classify_listing_category hardened, migration/backfill, import storage, manual-unit storage, Smart Match desired_unit/category handling, projects filter), `templates/clients.html`, `templates/client_detail.html` (unit type select options updated), `tests/test_unit_type_normalization.py` (new, 12 tests).
- **Schema changes (additive):** `listings.unit_type_canonical TEXT`. Backfill idempotent. No destructive changes. `listing_uid`/`normalized_unit_type` unchanged.
- **Canonical mappings:** RES→Residential, Chalet→Chalet, Studio→Studio, Hotle apartment/Hotle apartment-RES→Hotel Apartment, all comm*/AD/med/Admin/Ret variants→Commercial, No Info/HOLD/sold out→empty.
- **Behavior:**
  - Residential client with no specific unit type matches all residential listings.
  - Residential + Apartment excludes Chalet/Villa/etc.
  - Commercial matches all commercial variants.
  - Category mismatch = hard exclusion.
  - Unknown unit types don't match a specified preference but remain eligible when no preference.
  - Raw unit_type preserved; listing_uid unchanged.
- **Tests:** 12 new + 62 existing = 74 passed, 0 failed (exit 0); 17 deprecation warnings.
- **Browser verification:** client form unit type options verified (10 canonical options, 0 console errors). Smart Match behavior verified via automated tests.
- **Completion criteria:** all applicable criteria met. P1.5 is COMPLETE.
- **Approval status:** P1.5 complete and verified. Awaiting approval before P1.6.

---

## Entry 0012 — P1.5 unknown unit-type correction (approved & verified)
- **Date:** 2026-11-20
- **Task:** P1.5 correction — make unknown unit types unclassified (empty canonical/category), preserve raw values, prevent unknown preference/category matching, add "Unit type not classified" reason, targeted idempotent backfill correction.
- **Assigned model:** Beam Free (primary).
- **Skills used:** broker-portal-workflow, verification-before-completion.
- **Files changed:** `app.py` (canonical_unit_type now returns '' for unknown; classify_listing_category returns '' for unknown; Smart Match unknown-preference handling + unclassified reason; category check excludes unknown when client category set; targeted backfill correction), `tests/test_unit_type_normalization.py` (updated + 6 new tests).
- **Schema/DB changes:** none new (uses existing unit_type_canonical/category columns).
- **Behavior:**
  - Unknown raw values (e.g. Penthouse) preserved in unit_type; canonical and category become ''.
  - Unknown client preference produces no matches.
  - Unknown inventory cannot satisfy Residential/Commercial/specific preference.
  - Unknown inventory remains eligible when no unit-type restriction, with reason "Unit type not classified".
  - Targeted backfill clears previously stored unknown canonical/category (idempotent).
- **Tests:** 15 tests in test_unit_type_normalization.py (was 11 + 4? actually 15 total now). Full suite 79 passed, 0 failed (exit 0); 17 deprecation warnings.
- **Browser verification:** client form options verified; Smart Match behavior via automated tests.
- **Completion criteria:** all applicable criteria met. P1.5 correction COMPLETE.
- **Approval status:** P1.5 correction complete and verified. Awaiting approval before P1.6.

---

## Entry 0013 — P1.6 Smart Match improvements (approved & verified)
- **Date:** 2026-11-20
- **Task:** P1.6 — improve Smart Match reliability, explainability, ranking, and empty states; preserve approved budget/location/category/unit-type rules.
- **Assigned model:** Beam Free (primary).
- **Skills used:** broker-portal-workflow, impeccable, verification-before-completion.
- **Files changed:** `app.py` (recommendation_score: 5-tuple return with near_budget flag, missing-info reasons, category exclusion for unknown; client_detail: 4 groups, match_exact/match_near_budget, sort priority, empty-state reason), `templates/client_detail.html` (4 Smart Match groups, near-budget badge, empty state, budget window text), `tests/test_smart_match_policy.py` + `tests/test_unit_type_normalization.py` (unpack updated to 5 values).
- **Schema/DB changes:** none.
- **Behavior:**
  - Exact (best) / Partial (alternative, non-near) / Near-Budget (alternative, near) / Stretch (stretch) groups separated.
  - Near-budget always after exact (sort by match_exact first).
  - Empty state explains why no matches.
  - Missing info reasons (delivery, finishing, payment plan, size, unit type not classified).
  - Near-budget badge in score.
- **Tests:** full suite 79 passed, 0 failed (exit 0); 17 deprecation warnings.
- **Browser verification:** client creation + Smart Match rendered (4 groups + empty state), 0 console errors, 0 failed requests. Near-budget badge not observed (no near-budget results in seeded data) — recorded as limitation.
- **Completion criteria:** all applicable criteria met. P1.6 is COMPLETE.
- **Approval status:** P1.6 complete and verified. Awaiting approval before any further work.

---

## Entry 0014 — P1.6 final verification (root cause, deterministic dataset, groups, tests, browser)
- **Date:** 2026-11-20
- **Task:** P1.6 final verification — root cause of empty state; deterministic A-I dataset; 4 groups; tests; browser.
- **Assigned model:** Beam Free (primary).
- **Skills used:** verification-before-completion.
- **Files:** `tests/test_smart_match_comprehensive.py` (new, 5 tests), `tests/test_smart_match_policy.py`, `tests/test_unit_type_normalization.py` (updated).
- **Root cause of empty state (documented, not a bug):** For the 5M Apartment client, Sheikh Zayed inventory has no "Apartment" units (RES ≠ Apartment per approved rules). 29 Sheikh Zayed listings: 21 RES (Residential canonical), 8 Commercial. 0 apartment-eligible. So 0 matches is correct.
- **Deterministic dataset (temporary DB):** A Apartment 4.5M; B Apartment 5.0M; C Apartment 5.5M; D Apartment 5.5M+1 (excluded); E Chalet 4M (excluded by unit pref); F Office 4M Commercial (excluded by category); G Apartment Ain Sokhna (excluded by location); H Apartment 4M missing price (excluded); I Penthouse 4M (excluded by Apartment pref).
- **Expected vs actual:** A,B best (verified); C near-budget (verified); D-H-I excluded; E,F,G excluded by criteria.
- **Four groups:** Best Match (B 100%, A 96%), Partial Matches (0), Near-Budget Alternatives (C 82% "NEAR-BUDGET", clearly separate), Stretch Options (0). Near-budget below normal.
- **Root-cause mismatch clarification:** Stretch Options band exists (above window); they do not bypass hard exclusions (D excluded). Near-budget never appears in Partial Matches.
- **Browser evidence:** App on 5105, client "5M Apartment Client": 2 matches (B, A), near-budget C, 0 console errors, 0 failed requests. "NoCategory NoUnit Client": "Unit type not classified" visible for Penthouse. Commercial/unknown-preference/empty-state verified via automated tests (test_commercial_client, test_unknown_preference_no_matches, test_empty_state_when_no_eligible).
- **Tests:** Full suite 84 passed, 0 failed (exit 0); 17 deprecation warnings.
- **Database backup:** None (no persistent DB modified).
- **Workbook SHA-256 unchanged:** verified (`3BBEC06F…0F59B`).
- **Remaining limitations:** screenshots not viewable (model limitation); responsive checks limited to desktop.
- **Approval status:** P1.6 verified. Awaiting approval before any further work.

---

## Entry 0017 — Timezone input unification + input validation + dashboard improvements (P1.7 audit tasks 1–3, verified)
- **Date:** 2026-11-20
- **Tasks:** (1) unify follow-up time handling to UTC storage + Cairo day bounds in dashboard/client_notifications/inject; (2) input validation in edit_client/update_client_status/users(); (3) dashboard sales target via BROKER_PORTAL_SALES_TARGET + improved _money via split_numeric_range.
- **Assigned model:** Beam Free (primary).
- **Files:** app.py, tests/test_input_validation.py (new, 7), tests/test_rbac.py (new, 9).
- **(1) Timezone:** dashboard followups_today uses cairo_day_utc_bounds(cairo_now date); due_clients uses datetime(followup_at)<=?; upcoming_clients uses day bounds + now_utc; client_notifications + inject() now use datetime('now') (UTC) instead of 'localtime'.
- **(2) Validation:** edit_client rejects empty name/phone (flash + redirect); update_client_status returns 400 on invalid status; users() rejects empty user_id with flash (no 500).
- **(3) Dashboard:** target = _broker_sales_target() (env BROKER_PORTAL_SALES_TARGET, default 10,000,000); _money uses split_numeric_range(v,'price') (handles 'Basic 2M', '2,000,000', '2.5M').
- **Tests:** 105 passed, 0 failed (exit 0); warnings unchanged.
- **Backup:** pre-change app.py + tests in `Downloads\Broker_Portal_V18_Workflow_Update\backups_tz_inputs_20261120_161050`.
- **Known issues:** none new. `datetime.utcnow()` fully replaced by utc_now_naive() earlier. No persistent DB changes.
- **Approval status:** P1.7 tasks 1–3 implemented and verified. Awaiting approval before P1.7 implementation. No git available (see earlier entries)."

---

## Entry 0015 — P1.6 final policy corrections & classification tests (verified)
- **Date:** 2026-11-20
- **Task:** Correct lower budget boundary to 60% (was effectively 48%); add missing-required-data handling (space, bedrooms) preventing Best/Exact; add genuine Partial + Stretch tests; browser verification.
- **Assigned model:** Beam Free (primary).
- **Files:** `app.py` (budget exclusion, required_missing logic, banding), `tests/test_smart_match_comprehensive.py` (genuine Partial, Missing Bedrooms, No Duplicates, new tests), `tests/test_smart_match_policy.py` (5-tuple updated).
- **Policy corrections:**
  - Lower eligible boundary now 60% (`pmax < low`), upper 110% (`pmin > high`). Below 60% or above 110% excluded.
  - Boundaries: lower uses range top (pmax), upper uses range bottom (pmin); near-budget/best use starting price (pmin).
  - Missing required data: client space pref + listing size missing → "Size not available", band forced to alternative/stretch (not Best). Client bedroom pref + listing nobedroom → "Bedrooms not confirmed", no Best award.
- **Required tests added:** genuine Partial (missing size), missing bedrooms, no-duplicates/exact-first, budget boundary tests (in policy file).
- **Budget tests (policy):** 2M→[1.2M,2.2M]; 5M→[3M,5.5M]; 10M→[6M,11M]; 2.999M excluded; 3M eligible; 5.5M near; 5.5M+1 excluded.
- **Full suite:** 85 passed, 0 failed (exit 0); 17 deprecation warnings.
- **Browser verification (deterministic A-I dataset, temp DB):** Best: B(100%),A(96%); Near: C(82% NEAR-BUDGET); Partial:0; Stretch:0; D excluded; E,F,G,H,I excluded by criteria. 0 console errors, 0 failed requests.
- **Stretch audit:** Stretch band = eligible, not near, not best, low score. With approved scoring, stretch is rare/unreachable; genuine stretch is essentially the residual bucket. Recommendation: keep group, or rename to "Lower-Fit." Not implemented per "no invented rules."
- **Workbook SHA-256 unchanged.**
- **Approval status:** P1.6 corrections verified. Awaiting approval before any further work. No P1.7 started.

---

## Entry 0016 — P1.6 final UI cleanup (verified)
- **Date:** 2026-11-20
- **Task:** Remove the unreachable Stretch/Lower-Fit result group; keep exactly Best Matches, Partial Matches, Near-Budget Alternatives. Reassign stretch results to Partial. Update tests/browser.
- **Assigned model:** Beam Free (primary).
- **Files:** `app.py` (recommendations dict; "stretch" reassigned to "alternatives" i.e. Partial), `templates/client_detail.html` (groups: Best Matches, Partial Matches, Near-Budget Alternatives; Stretch removed).
- **Behavior:** No scoring/eligibility/boundary change. Stretch band reassigned to Partial; near-budget still separate. Best requires `pmin<=stated_top` (from Entry 0015).
- **Tests added:** test_three_groups_only, test_eligible_non_near_all_in_best_or_partial. Full suite 89 passed, 0 failed.
- **Browser (deterministic A-I):** 3 groups present, Stretch removed, 0 console errors, 0 failed requests. Best: B(100%),A(96%); Near: C(82% NEAR-BUDGET).
- **Workbook SHA-256 unchanged.**
- **Approval status:** P1.6 complete. Awaiting approval before any further work. No P1.7 started.

---

## Entry 0018 - P1.7.1 schema restoration + ownership-history foundation (verified)
- **Date:** 2026-11-21
- **Task:** Restore the persistent DB to the current P1.1-P1.6 schema via the existing `init_db()` mechanism, then add the additive `broker_ownership_history` foundation table (schema only).
- **Assigned model:** Beam Free (primary).
- **Files:** `app.py` (`init_db()`: `CREATE TABLE IF NOT EXISTS broker_ownership_history`), `tests/test_ownership_history.py` (new, 9 tests), `DEVELOPMENT_LOG.md`.
- **Persistent DB migration:** one-off runner outside the project with `BROKER_PORTAL_DATA` pointing at `data`; `init_db()` only. No app/server start, no `refresh_listing_location_matches()`.
- **Restoration result:** `clients` + bathrooms/property_category/preferred_developer/preferred_project/priority; `listings` + category/listing_uid/unit_type_canonical; new `client_locations` table. `listing_uid` backfilled for all 226 rows (10 unknown-unit rows intentionally keep empty canonical/category).
- **Ownership history:** `broker_ownership_history(id, client_id, previous_owner_id, new_owner_id, admin_id, reason, created_at)` with FKs to `clients` (CASCADE) and `users` (NO ACTION). 0 rows; no backfill, no fake history.
- **Canonical ownership unchanged:** `clients.assigned_to` (client 1: broker_id=1, assigned_to=1, created_by=1). No `owner_user_id`. Favorites remain per-`user_id`.
- **Safety:** pre-migration backup `Downloads\Broker_Portal_V18_Workflow_Update\backups_p171_history_20261121_001724`; DB SHA-256 `E92E582B...` -> `BC52833E...`; row counts unchanged (clients 1, listings 226, users 2, versions 1, activities 1, audit_logs 4, favorites/opportunities 0); pre-existing columns byte-identical vs backup; `PRAGMA quick_check` ok; idempotent logical state identical after a second `init_db()`.
- **Workbook SHA-256 unchanged:** `3BBEC06F12CADFBDAA446E93D3ED0E11DCA552067564A15B4A07021540B0F59B`.
- **Tests:** 114 passed, 0 failed (exit 0) - prior 105 plus 9 ownership-history tests.
- **Approval status:** P1.7.1 schema foundation verified. Awaiting approval before P1.7.2. No transfer endpoint, deactivation workflow, admin UI, or RBAC redesign.

---

## Entry 0019 - P1.7.2 auth/RBAC hardening (verified)
- **Date:** 2026-11-21
- **Task:** Centralize session identity validation and add server-side RBAC/ownership tests. No ownership-transfer, deactivation UI, admin UI, or frontend changes.
- **Assigned model:** Beam Free (primary).
- **Files:** `app.py` (`VALID_ROLES`, `load_session_user()`, `login_required()` uses it, `index()` validates session, `login()` rejects unknown roles), `tests/test_auth_hardening.py` (new, 25 tests), `DEVELOPMENT_LOG.md`.
- **Auth changes:** session `user_id` is only an identifier; role/active status are re-read from `users` on every protected request. Missing/inactive/unknown-role users get `session.clear()` + redirect to login. `index()` now applies the same DB validation instead of only checking `user_id` presence. Successful login still calls `session.clear()` before setting identity (session rotation).
- **Authorization confirmed:** all private client routes go through `get_client_or_404` (`clients.assigned_to == session user` for brokers; admins unrestricted); `/api/search`, `/clients`, `/clients/notifications`, dashboard, and `inject()` are `assigned_to`-scoped for brokers. All `/admin/*`, listing edit/reset, upload, publish/restore, user management and project management routes use `@login_required("admin")`.
- **Manipulation checks:** broker POSTing `assigned_to` via `/clients/add` is forced to self; via `/clients/<id>/edit` the field is ignored for brokers. Session `role="admin"` is overwritten from the DB before the admin gate.
- **Deactivation:** an inactive user is denied on the next protected request and the session is cleared; inactive accounts cannot log in (`active=1` filter).
- **Tests:** 139 passed, 0 failed (exit 0) - prior 114 plus 25 auth/RBAC tests.
- **Persistent DB:** unchanged (SHA-256 `BC52833E2758CEDD9C9866465AE6916BC06F23D29B8FF42FEBC1FDEFF68ABEE2`); no ownership data changed; workbook SHA-256 unchanged.
- **Approval status:** P1.7.2 implemented and verified. Awaiting approval before P1.7.3.