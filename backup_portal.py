"""Consistent backup of the Broker Portal data directory (stdlib only)."""
import datetime
import os
import shutil
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("BROKER_PORTAL_DATA", str(BASE / "data"))).expanduser().resolve()
DB = DATA / "broker_portal.db"
BACKUPS = DATA / "backups"
LOGS = DATA / "logs"
KEEP = 30


def _log(msg):
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        with (LOGS / "backup.log").open("a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().isoformat()} {msg}\n")
    except Exception:
        pass


def main():
    try:
        if not DB.exists():
            raise RuntimeError(f"database not found: {DB}")
        BACKUPS.mkdir(parents=True, exist_ok=True)
        LOGS.mkdir(parents=True, exist_ok=True)

        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_dir = BACKUPS / stamp
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_db = dest_dir / "broker_portal.db"

        src = sqlite3.connect(str(DB))
        try:
            dst = sqlite3.connect(str(dest_db))
            try:
                src.backup(dst)
                dst.commit()
            finally:
                dst.close()
        finally:
            src.close()

        # integrity check on the copy
        chk = sqlite3.connect(str(dest_db))
        try:
            ok = chk.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            chk.close()
        if ok != "ok":
            raise RuntimeError(f"backup integrity check failed: {ok}")

        # copy session secret
        secret = DATA / ".session_secret"
        if secret.exists():
            shutil.copy2(secret, dest_dir / ".session_secret")

        # copy uploads
        uploads = DATA / "uploads"
        if uploads.exists():
            shutil.copytree(uploads, dest_dir / "uploads", dirs_exist_ok=True)

        # prune old backups (keep last KEEP)
        dirs = sorted([p for p in BACKUPS.iterdir() if p.is_dir()], key=lambda p: p.name)
        while len(dirs) > KEEP:
            old = dirs.pop(0)
            shutil.rmtree(old, ignore_errors=True)

        _log(f"OK backup created at {dest_dir}")
        print(f"Backup created: {dest_dir}")
        return 0
    except Exception as exc:
        _log(f"FAIL {exc}")
        print(f"Backup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
