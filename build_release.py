"""Build a clean release ZIP of Broker Portal."""
import datetime
import os
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
NAME = "Broker_Portal_Release_" + datetime.datetime.now().strftime("%Y%m%d") + ".zip"
OUT = BASE / NAME

INCLUDE_FILES = ["app.py", "requirements.txt", "run_portal.bat", "run_office.bat",
                 "backup_portal.bat", "backup_portal.py", "reset_admin_password.py",
                 "README.md", "README.txt", "OFFICE_SETUP.md"]
INCLUDE_DIRS = ["templates", "static"]

EXCLUDE_NAMES = {".venv", "bp_testdeps", "backups", "data", ".opencode", "tests",
                 "__pycache__", ".git", "node_modules"}
EXCLUDE_EXT = {".db", ".session_secret", ".xlsx", ".pyc"}


def allowed(path: Path):
    if any(part in EXCLUDE_NAMES for part in path.parts):
        return False
    if path.suffix in EXCLUDE_EXT:
        return False
    name = path.name
    if name.startswith("."):
        return False
    return True


def main():
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for f in INCLUDE_FILES:
            p = BASE / f
            if p.exists():
                z.write(p, f)
        for d in INCLUDE_DIRS:
            root = BASE / d
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_file() and allowed(path):
                    arc = path.relative_to(BASE).as_posix()
                    z.write(path, arc)
    print(f"Created {OUT}")
    # verify
    with zipfile.ZipFile(OUT) as z:
        names = z.namelist()
        bad = [n for n in names if any(x in n.split("/") for x in EXCLUDE_NAMES) or n.endswith(tuple(EXCLUDE_EXT))]
        print(f"Entries: {len(names)}; forbidden: {len(bad)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
