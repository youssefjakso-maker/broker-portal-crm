> **V17:** see `CHANGES_V17.txt` (Smart Match fix for wide price ranges + security hardening).

# Broker Portal â€” Final Workspace Release

A private real-estate brokerage workspace for Admins and Brokers. It combines the company's Excel inventory with Admin-created projects/units and a broker CRM in one application.

## What is included

### Inventory and projects
- One Projects view groups inventory by project; opening a project shows its units.
- Excel `.xlsx` / `.xlsm` upload, draft validation, publish, archive and restore.
- The importer understands the workbook's original headers (including existing misspellings such as `Sapce`, `Dlivery date`, `Finshing`, `Porject Location`, and `Compeny loction`). Original source values and extra columns are retained.
- Admin-only manual project creation, project editing, unit creation, unit editing, and project archive/restore. Manually created units are stored independently of Excel versions and remain available when a new Excel version is published.
- Admin-only listing overrides retain the original Excel values, show the final values, and keep a change history. Individual fields can be reset to the source value.
- The included workbook `data/projects Upated9-11 (1).xlsx` is a source copy for convenience; it is **not** imported or published automatically. Upload it through Data Management when ready.

### Smart Match
- Rule-based, local recommendations grouped as Best Match, Good Alternatives, and Stretch Options, with reasons for each result.
- Client Preferred Location is a dropdown populated from the currently active Excel inventory plus active Admin-created units. It uses the portal's controlled area labels and keeps Sheikh Zayed and New Zayed separate.
- The workbook's `RES` unit category is represented in client qualification as `Residential (RES)`. It remains distinct from `Apartment`; the source does not label every `RES` row as an Apartment.
- Budget flexibility: Strict = 90â€“130% of target; Flexible = 80â€“160%; Very Flexible = 70â€“180%.
- Preferred unit type and location are used in matching. Sheikh Zayed and New Zayed are separate areas; `zayed` maps to Sheikh Zayed, while `new zayed` remains New Zayed.
- Space matching allows nearby sizes; very broad total-price ranges are excluded from recommendations rather than treated as exact matches.
- Recommendations search the current published Excel inventory and active Admin-created units.

### CRM and ownership
- Client qualification, lead source, temperature, preferred area/unit/size, budget flexibility, next action, follow-up date, notes, activity timeline and opportunities.
- A broker sees only clients currently assigned to that broker. Admin can see all clients.
- `Created By` remains the original creator. `Assigned To` is the current owner and can be changed by Admin.
- When Admin transfers a client, the new broker gains access and the previous broker loses access. Activities and opportunities follow the same client access rules.
- Dashboard follow-ups, client notifications, global search, quick Add-to-Client, favorites, WhatsApp summaries and payment calculator.

### Roles and permissions

**Admin** can manage Excel inventory, publish/restore versions, create and manage manual projects/units, edit/reset listing overrides, create/disable broker accounts, reset broker passwords, transfer clients, and view the Audit Log.

**Broker** can browse published/active inventory, use Smart Match and the payment calculator, and manage only their assigned clients, opportunities, activities and follow-ups. Brokers cannot create/edit/delete inventory or access Admin routes. These restrictions are checked on the server as well as hidden in the interface.

## First run on Windows

1. Install Python 3.10 or newer and enable **Add Python to PATH**.
2. Extract the ZIP into a folder where the team account can read/write.
3. Double-click `run_portal.bat`. It creates a local virtual environment and installs the packages in `requirements.txt`.
4. On the host computer, open `http://127.0.0.1:5000`.
5. The portal forces you to change the default password at first login.

For a fresh database, the default accounts are:

| Role | Email | Initial password |
|---|---|---|
| Admin | `admin@local` | Set during first-run setup |
| Broker | `broker@local` | Set during first-run setup |

New and reset broker passwords must be at least 10 characters. Existing databases keep their existing accounts and password hashes; the defaults are created only when the database has no Admin account.

## Using it with the broker team

The batch file now listens on `127.0.0.1` (this computer only) by default. To let other computers on the office network connect, set `BROKER_PORTAL_HOST=0.0.0.0` before running. Other computers on the **same private office network** can connect. On the host computer, run `ipconfig` and find its IPv4 address. Brokers open `http://HOST-PC-IP:5000` in their browsers. Allow inbound TCP port `5000` through Windows Firewall on the host if required.

Keep the host computer running while the team uses the portal. Everyone must connect to this **one hosted instance** so that all users share the same `data/broker_portal.db`; do not run separate copies on every broker's computer, or their data will diverge.

This package is intended for a private LAN or private VPN. It is not configured for direct public-Internet exposure or HTTPS. Do not forward port 5000 to the public Internet. For remote access, use an organization-managed VPN/private network.

## Data, upgrades and backups

- The SQLite database, uploaded Excel files and session secret are stored in `data/`.
- Back up the entire `data/` folder regularly. For a consistent backup, stop the portal before copying it.
- When installing a newer release, stop the portal, keep the existing `data/` folder, replace the application files, then start it again. Do not overwrite the live database with a blank one.
- On first startup, the app initializes/migrates the database. Existing user accounts, imported versions and CRM records are preserved by the supported migrations.
- The session secret is generated locally on first startup and saved in `data/.session_secret`; keep it with the database between restarts/backups.

## Workbook validation note

The included source workbook was checked with the current importer: 218 rows imported, 0 rejected, 0 serious errors, 2 warnings and 68 informational notes. Informational notes do not block publishing; serious errors do. Review the actual draft summary in Data Management before publishing any updated workbook.

## Open Source`r`n`r`nBroker Portal is an open-source CRM and inventory management project built around real-world brokerage workflows. The project focuses on role-based access control, client ownership, auditability, inventory management, Smart Match recommendations, and security-focused testing. Contributions, issues, and feedback are welcome.`r`n`r`n## Important operating notes

- The payment calculator is indicative only. Always confirm the developer's current payment plan, fees, maintenance and availability before quoting a client.
- Manual projects/units are part of the same broker inventory and recommendation search as the published Excel data, but are not deleted or replaced when Excel is republished.
- This is a local internal workspace. Keep regular backups and restrict access to trusted team members.


