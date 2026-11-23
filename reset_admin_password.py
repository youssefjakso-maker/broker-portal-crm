"""Reset an admin password on the host machine (interactive)."""
import getpass
import os
import sqlite3
import sys
from pathlib import Path
from werkzeug.security import generate_password_hash

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("BROKER_PORTAL_DATA", str(BASE / "data"))).expanduser().resolve()
DB = DATA / "broker_portal.db"
DEFAULTS = {"Admin123!", "Broker123!"}


def main():
    if not DB.exists():
        print(f"Database not found: {DB}", file=sys.stderr)
        return 1
    email = input("Admin email: ").strip().lower()
    if not email:
        print("Email required.", file=sys.stderr)
        return 1
    pw = getpass.getpass("New password: ")
    pw2 = getpass.getpass("Confirm: ")
    if pw != pw2:
        print("Passwords do not match.", file=sys.stderr)
        return 1
    if len(pw) < 10:
        print("Password must be at least 10 characters.", file=sys.stderr)
        return 1
    if pw in DEFAULTS:
        print("Password must not be a shipped default.", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(DB))
    try:
        row = conn.execute("SELECT id, role FROM users WHERE lower(email)=?", (email,)).fetchone()
        if not row or row[1] != "admin":
            print("Admin account not found.", file=sys.stderr)
            return 1
        uid = row[0]
        conn.execute(
            "UPDATE users SET password_hash=?, must_change_password=1 WHERE id=?",
            (generate_password_hash(pw), uid),
        )
        conn.execute(
            "INSERT INTO audit_logs(actor_id, action, entity_type, entity_id, details, created_at) VALUES(?,?,?,?,?,?)",
            (uid, "Reset admin password (host)", "user", str(uid), "host reset", __import__("datetime").datetime.now().isoformat()),
        )
        conn.commit()
        print("Admin password reset. User must change password on next login.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
