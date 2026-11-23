"""Pre-launch cleanup. STOP the portal first. Asks before every deletion; makes a backup first."""
import os, shutil, sqlite3, datetime
from pathlib import Path
from werkzeug.security import check_password_hash

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("BROKER_PORTAL_DATA", BASE / "data"))
DB = DATA / "broker_portal.db"
DEFAULTS = {"admin@local": "Admin123!", "broker@local": "Broker123!"}

def ask(q): return input(q + " [y/N] ").strip().lower() == "y"

bk = DATA / "backups" / ("pre_cleanup_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
bk.mkdir(parents=True, exist_ok=True)
shutil.copy2(DB, bk / "broker_portal.db")
print("Backup saved:", bk)

c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
c.execute("PRAGMA foreign_keys=ON")

print("\n== Default accounts ==")
for u in c.execute("SELECT id,email,role FROM users").fetchall():
    d = DEFAULTS.get(u["email"])
    if d and check_password_hash(c.execute("SELECT password_hash FROM users WHERE id=?", (u["id"],)).fetchone()[0], d):
        print(f"{u['email']} ({u['role']}) still uses the default password.")
        if u["role"] == "broker" and ask("  Delete this account?"):
            owned = c.execute("SELECT COUNT(*) FROM clients WHERE assigned_to=? OR created_by=?", (u["id"], u["id"])).fetchone()[0]
            if owned:
                print(f"  SKIPPED: owns {owned} client(s). Deactivate it from the Admin page instead.")
            else:
                try:
                    c.execute("DELETE FROM users WHERE id=?", (u["id"],)); print("  deleted.")
                except sqlite3.Error as e:
                    c.execute("UPDATE users SET active=0 WHERE id=?", (u["id"],)); print("  could not delete (history exists) -> deactivated.")

print("\n== Clients ==")
for cl in c.execute("SELECT id,name,phone,created_at FROM clients").fetchall():
    print(f"#{cl['id']} {cl['name']} / {cl['phone']} / {cl['created_at'][:10]}")
    if ask("  Delete this client and its activities/opportunities?"):
        for t in ("activities", "opportunities", "favorites"):
            try: c.execute(f"DELETE FROM {t} WHERE client_id=?", (cl["id"],))
            except sqlite3.Error: pass
        try: c.execute("DELETE FROM client_locations WHERE client_id=?", (cl["id"],))
        except sqlite3.Error: pass
        c.execute("DELETE FROM clients WHERE id=?", (cl["id"],)); print("  deleted.")

c.commit()
print("\nDone. Quick check:", c.execute("PRAGMA quick_check").fetchone()[0])
