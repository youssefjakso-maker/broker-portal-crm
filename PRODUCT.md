# PRODUCT.md — Broker Portal CRM

**Status:** Inferred from the user's comprehensive redesign brief (2026-11-19). No interactive interview was run; assumptions are labeled below.

## Product
Broker Portal CRM is a private, single-host real-estate brokerage workspace for Admins and Brokers. It combines the company's Excel inventory with Admin-created projects/units and a broker CRM (clients, opportunities, follow-ups, favorites, Smart Match).

## Users
- **Admin:** manages Excel inventory, versions, manual projects/units, listing overrides, user accounts, audit log.
- **Broker:** browses inventory, runs Smart Match, manages assigned clients/opportunities/activities/follow-ups.

## Platform
Web (desktop-first, responsive). Python/Flask/Jinja2/SQLite. No frontend framework. Private LAN/VPN only.

## Mode (Impeccable)
- **Operate** for the CRM workspace (scanability, consistency, native expectations).
- **Persuade** only for the login surface.

## Goals
- Complete, useful client profiles (multiple preferred locations, total budget, property category, preferences).
- Reliable Smart Match using real inventory.
- Organized real-estate inventory and projects.
- Useful business dashboard.
- Functional opportunities and follow-ups.
- Consistent Luxury Editorial design: Charcoal Black #242424 + Bone White #F1EBDD + Barber Red #C62832, hybrid dark-nav/light-workspace.

## Assumptions (inferred, not confirmed by interview)
- Single-tenant, single-host; no multi-org.
- Arabic/English mixed UI text is possible (existing templates use English labels; some Arabic in governance). Typography must handle both.
- No public-internet deployment; HTTPS optional via env.
- Primary workflow is desktop; mobile is secondary but must not break.

## Non-goals
- No framework migration (React/Vue).
- No new package managers or build tooling.
- No schema changes without approval (additive migrations only, already approved in scope).