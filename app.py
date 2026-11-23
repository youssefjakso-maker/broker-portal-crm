from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from pathlib import Path
import sqlite3, json, re, os, uuid, shutil, secrets, traceback, time, hmac
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from openpyxl import load_workbook

BASE = Path(__file__).resolve().parent


def _resolve_data_dir():
    """Resolve the storage directory, allowing tests to stay out of project data.

    BROKER_PORTAL_DATA overrides the default <project>/data folder. When the
    variable is unset, behaviour is identical to previous releases.
    """
    override = os.environ.get("BROKER_PORTAL_DATA")
    if override:
        return Path(override).expanduser().resolve()
    return BASE / "data"


DATA = _resolve_data_dir()
UPLOADS = DATA / "uploads"
DB = DATA / "broker_portal.db"
DATA.mkdir(parents=True, exist_ok=True)
UPLOADS.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
# Keep uploads bounded and fail with a visible message rather than an endless wait.
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024


def upload_log(message):
    """Write upload-stage diagnostics to both CMD and a local log file."""
    stamp = utc_now_naive().isoformat(timespec="seconds") + "Z"
    line = f"[{stamp}] [UPLOAD] {message}"
    try:
        (DATA / "upload_debug.log").parent.mkdir(parents=True, exist_ok=True)
        with (DATA / "upload_debug.log").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def session_secret():
    configured = os.environ.get("BROKER_PORTAL_SECRET")
    if configured:
        return configured
    secret_path = DATA / ".session_secret"
    try:
        if secret_path.exists():
            saved = secret_path.read_text(encoding="utf-8").strip()
            if saved:
                return saved
        generated = secrets.token_urlsafe(48)
        secret_path.write_text(generated, encoding="utf-8")
        try:
            os.chmod(secret_path, 0o600)
        except OSError:
            pass
        return generated
    except OSError:
        # Environment configuration is recommended for hosted deployments.
        return secrets.token_urlsafe(48)

app.secret_key = session_secret()


def _load_timezone(key):
    """Load a timezone, failing with an actionable message when tzdata is absent."""
    try:
        return ZoneInfo(key)
    except Exception as exc:  # pragma: no cover - only reached without tzdata
        raise RuntimeError(
            f"Timezone database is unavailable: could not load {key!r}. "
            "On Windows this usually means the 'tzdata' package is missing. "
            "Run run_portal.bat, or install requirements with "
            "'python -m pip install -r requirements.txt', then start the portal again."
        ) from exc


CAIRO_TZ = _load_timezone("Africa/Cairo")

def cairo_now():
    return datetime.now(CAIRO_TZ)

def display_dt(value):
    if not value:
        return "—"
    raw=str(value).replace("Z", "")
    try:
        dt=datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            # Existing stored timestamps are UTC-naive.
            dt=dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(CAIRO_TZ).strftime("%d %b %Y · %I:%M %p")
    except Exception:
        return str(value).replace("T", " ")[:16]

app.jinja_env.filters["display_dt"] = display_dt


def utc_naive_to_cairo_local_str(value):
    """Convert a stored UTC-naive timestamp to a Cairo-local datetime-local string."""
    if not value:
        return ""
    raw = str(value).replace("Z", "").replace(" ", "T")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CAIRO_TZ).strftime("%Y-%m-%dT%H:%M")


def cairo_local_to_utc_naive(value):
    """Convert a user-entered Cairo-local datetime string to a UTC-naive ISO string.

    Returns (utc_iso_string, None) on success, or (None, error_message) when the
    input is invalid or refers to an ambiguous/nonexistent local time during a
    DST transition.
    """
    s = clean(value)
    if not s:
        return "", None
    raw = s.replace(" ", "T")
    try:
        naive = datetime.fromisoformat(raw)
    except ValueError:
        return None, "Invalid date/time format."
    if naive.tzinfo is not None:
        naive = naive.replace(tzinfo=None)
    # Detect ambiguous (two possible offsets) or nonexistent (gap) local times.
    off0 = naive.replace(tzinfo=CAIRO_TZ, fold=0).utcoffset()
    off1 = naive.replace(tzinfo=CAIRO_TZ, fold=1).utcoffset()
    if off0 != off1:
        return None, "The selected date/time is ambiguous or invalid in Cairo time (daylight-saving transition). Please choose a different time."
    dt = naive.replace(tzinfo=CAIRO_TZ, fold=0)
    utc = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return utc.isoformat(), None


def cairo_day_utc_bounds(day=None):
    """Return (start_utc_naive_iso, end_utc_naive_iso) for a Cairo calendar day."""
    if day is None:
        d = cairo_now().date()
    else:
        d = datetime.strptime(str(day), "%Y-%m-%d").date()
    from datetime import date as _date, timedelta as _td
    next_d = d + _td(days=1)
    start_local = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=CAIRO_TZ)
    end_local = datetime(next_d.year, next_d.month, next_d.day, 0, 0, 0, tzinfo=CAIRO_TZ)
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc.isoformat(), end_utc.isoformat()

app.jinja_env.filters["cairo_input"] = utc_naive_to_cairo_local_str

# ---------------------------------------------------------------- security layer
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("BROKER_PORTAL_HTTPS", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)

DEFAULT_PASSWORDS = {"admin@local": "Admin123!", "broker@local": "Broker123!"}
_FORM_POST_RE = re.compile(r"(<form\b[^>]*\bmethod\s*=\s*[\"']?post[\"']?[^>]*>)", re.I)


def get_csrf_token():
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token

app.jinja_env.globals["csrf_token"] = get_csrf_token


@app.before_request
def csrf_protect():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
        expected = session.get("_csrf", "")
        if not expected or not sent or not hmac.compare_digest(str(sent), str(expected)):
            abort(400, description="Security token missing or expired. Go back, refresh the page and try again.")


@app.after_request
def security_headers(resp):
    # Auto-insert the CSRF token into every POST form of rendered HTML pages.
    if resp.mimetype == "text/html" and not resp.direct_passthrough:
        token = get_csrf_token()
        html = resp.get_data(as_text=True)
        html = _FORM_POST_RE.sub(lambda m: m.group(1) + f'<input type="hidden" name="csrf_token" value="{token}">', html)
        resp.set_data(html)
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("Content-Security-Policy",
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; img-src 'self' data:; frame-ancestors 'none'; form-action 'self'; base-uri 'self'")
    if request.endpoint != "static":
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


# Login throttle: 5 failures per (IP, email) within 15 minutes -> locked for the rest of the window.
_LOGIN_FAILS = {}
LOGIN_MAX_FAILS = 5
LOGIN_WINDOW = 15 * 60


def _login_key(email):
    return (request.remote_addr or "?", email)


def login_locked(email):
    now = time.time()
    fails = [t for t in _LOGIN_FAILS.get(_login_key(email), []) if now - t < LOGIN_WINDOW]
    _LOGIN_FAILS[_login_key(email)] = fails
    return len(fails) >= LOGIN_MAX_FAILS


def login_failed(email):
    _LOGIN_FAILS.setdefault(_login_key(email), []).append(time.time())


def login_succeeded(email):
    _LOGIN_FAILS.pop(_login_key(email), None)

CANON = {
    "non": "non",
    "developer name": "developer",
    "project name": "project",
    "location": "location",
    "price by meter": "price_m2",
    "price": "total_price",
    "sapce": "space",
    "space": "space",
    "payment plan": "payment_plan",
    "unit type": "unit_type",
    "dlivery date": "delivery",
    "delivery date": "delivery",
    "finshing": "finishing",
    "finishing": "finishing",
    "maintenance": "maintenance",
    "porject location": "project_location",
    "project location": "project_location",
    "compeny loction": "company_location",
    "company location": "company_location",
}

def db():
    conn = sqlite3.connect(DB, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn

def _rebuild_listings_for_manual_inventory(conn):
    """Migrate the listings table so manually-created units can live outside Excel versions.

    Existing listing ids are preserved, and the legacy opportunities/favorites
    foreign-key targets continue to point to the rebuilt `listings` table.
    """
    info = conn.execute("PRAGMA table_info(listings)").fetchall()
    columns = {r[1]: r for r in info}
    needs_rebuild = (
        not info
        or columns.get("version_id", [None, None, None, 0])[3] == 1
        or "source_type" not in columns
        or "manual_project_id" not in columns
        or "created_by" not in columns
        or "updated_by" not in columns
    )
    if not needs_rebuild:
        return

    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("PRAGMA legacy_alter_table=ON")
    conn.execute("ALTER TABLE listings RENAME TO listings_before_manual_inventory")
    conn.executescript("""
    CREATE TABLE listings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER,
        source_sheet TEXT,
        source_row INTEGER,
        original_json TEXT NOT NULL DEFAULT '{}',
        developer TEXT,
        project TEXT,
        location TEXT,
        price_m2_min REAL,
        price_m2_max REAL,
        total_price_min REAL,
        total_price_max REAL,
        space_min REAL,
        space_max REAL,
        payment_plan TEXT,
        unit_type TEXT,
        unit_type_canonical TEXT,
        category TEXT DEFAULT '',
        delivery TEXT,
        finishing TEXT,
        maintenance TEXT,
        project_location TEXT,
        company_location TEXT,
        normalized_developer TEXT,
        normalized_project TEXT,
        normalized_location TEXT,
        normalized_unit_type TEXT,
        manual_json TEXT DEFAULT '{}',
        manual_updated_at TEXT,
        source_type TEXT NOT NULL DEFAULT 'excel',
        listing_uid TEXT,
        manual_project_id INTEGER,
        created_by INTEGER,
        updated_by INTEGER,
        FOREIGN KEY(version_id) REFERENCES versions(id),
        FOREIGN KEY(manual_project_id) REFERENCES manual_projects(id)
    );
    """)
    new_cols = {r[1] for r in conn.execute("PRAGMA table_info(listings)").fetchall()}
    old_cols = {r[1] for r in conn.execute("PRAGMA table_info(listings_before_manual_inventory)").fetchall()}
    shared = [c for c in [
        "id", "version_id", "source_sheet", "source_row", "original_json", "developer", "project", "location",
        "price_m2_min", "price_m2_max", "total_price_min", "total_price_max", "space_min", "space_max",
        "payment_plan", "unit_type", "delivery", "finishing", "maintenance", "project_location", "company_location",
        "normalized_developer", "normalized_project", "normalized_location", "normalized_unit_type", "manual_json", "manual_updated_at",
        "listing_uid", "unit_type_canonical"
    ] if c in old_cols and c in new_cols]
    target = shared + [c for c in ["source_type", "manual_project_id", "created_by", "updated_by"] if c not in shared]
    select = shared[:]
    for c in target[len(shared):]:
        if c == "source_type": select.append("'excel'")
        else: select.append("NULL")
    conn.execute(
        f"INSERT INTO listings({','.join(target)}) SELECT {','.join(select)} FROM listings_before_manual_inventory"
    )
    conn.execute("DROP TABLE listings_before_manual_inventory")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_version ON listings(version_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_manual_project ON listings(manual_project_id)")
    conn.execute("PRAGMA legacy_alter_table=OFF")
    conn.execute("PRAGMA foreign_keys=ON")


def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin','broker')),
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        must_change_password INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS versions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('draft','live','archived')),
        created_at TEXT NOT NULL,
        created_by INTEGER,
        total_rows INTEGER DEFAULT 0,
        imported_rows INTEGER DEFAULT 0,
        rejected_rows INTEGER DEFAULT 0,
        warnings INTEGER DEFAULT 0,
        serious_errors INTEGER DEFAULT 0,
        summary_json TEXT
    );

    CREATE TABLE IF NOT EXISTS manual_projects(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project TEXT NOT NULL,
        developer TEXT DEFAULT '',
        location TEXT DEFAULT '',
        project_location TEXT DEFAULT '',
        company_location TEXT DEFAULT '',
        description TEXT DEFAULT '',
        active INTEGER NOT NULL DEFAULT 1,
        created_by INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(created_by) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS listings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id INTEGER,
        source_sheet TEXT,
        source_row INTEGER,
        original_json TEXT NOT NULL DEFAULT '{}',
        developer TEXT,
        project TEXT,
        location TEXT,
        price_m2_min REAL,
        price_m2_max REAL,
        total_price_min REAL,
        total_price_max REAL,
        space_min REAL,
        space_max REAL,
        payment_plan TEXT,
        unit_type TEXT,
        unit_type_canonical TEXT,
        category TEXT DEFAULT '',
        delivery TEXT,
        finishing TEXT,
        maintenance TEXT,
        project_location TEXT,
        company_location TEXT,
        normalized_developer TEXT,
        normalized_project TEXT,
        normalized_location TEXT,
        normalized_unit_type TEXT,
        manual_json TEXT DEFAULT '{}',
        manual_updated_at TEXT,
        source_type TEXT NOT NULL DEFAULT 'excel',
        listing_uid TEXT,
        manual_project_id INTEGER,
        created_by INTEGER,
        updated_by INTEGER,
        FOREIGN KEY(version_id) REFERENCES versions(id),
        FOREIGN KEY(manual_project_id) REFERENCES manual_projects(id)
    );

    CREATE TABLE IF NOT EXISTS clients(
        id INTEGER PRIMARY KEY AUTOINCREMENT, broker_id INTEGER NOT NULL,
        name TEXT NOT NULL, phone TEXT NOT NULL, project TEXT, offered_price TEXT,
        budget TEXT, unit_type TEXT, notes TEXT, followup_at TEXT,
        status TEXT NOT NULL DEFAULT 'Pending', source TEXT DEFAULT '', temperature TEXT DEFAULT 'Warm',
        preferred_location TEXT DEFAULT '', preferred_unit_type TEXT DEFAULT '', preferred_space_min REAL, preferred_space_max REAL,
        bedrooms TEXT DEFAULT '', bathrooms TEXT DEFAULT '', purpose TEXT DEFAULT '', budget_flexibility TEXT DEFAULT 'Flexible',
        next_action TEXT DEFAULT 'Follow Up', lost_reason TEXT DEFAULT '',
        property_category TEXT DEFAULT '', preferred_developer TEXT DEFAULT '', preferred_project TEXT DEFAULT '',
        priority TEXT DEFAULT 'Normal',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        created_by INTEGER, assigned_to INTEGER,
        FOREIGN KEY(broker_id) REFERENCES users(id),
        FOREIGN KEY(created_by) REFERENCES users(id),
        FOREIGN KEY(assigned_to) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS client_locations(
        client_id INTEGER NOT NULL,
        location TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(client_id, location),
        FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS opportunities(
        id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL, listing_id INTEGER,
        project TEXT DEFAULT '', unit_label TEXT DEFAULT '', offered_price TEXT DEFAULT '',
        status TEXT DEFAULT 'New', temperature TEXT DEFAULT 'Warm', notes TEXT DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE,
        FOREIGN KEY(listing_id) REFERENCES listings(id)
    );

    CREATE TABLE IF NOT EXISTS activities(
        id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL, opportunity_id INTEGER,
        activity_type TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL, created_by INTEGER,
        FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE,
        FOREIGN KEY(opportunity_id) REFERENCES opportunities(id)
    );

    CREATE TABLE IF NOT EXISTS favorites(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, listing_id INTEGER NOT NULL,
        created_at TEXT NOT NULL, UNIQUE(user_id, listing_id),
        FOREIGN KEY(user_id) REFERENCES users(id), FOREIGN KEY(listing_id) REFERENCES listings(id)
    );

    CREATE TABLE IF NOT EXISTS audit_logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actor_id INTEGER,
        action TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT,
        details TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY(actor_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS update_intelligence(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_text TEXT NOT NULL,
        summary_json TEXT NOT NULL DEFAULT '{}',
        created_by INTEGER,
        created_at TEXT NOT NULL,
        FOREIGN KEY(created_by) REFERENCES users(id)
    );

    -- P1.7.1: ownership transfer history foundation (schema only).
    -- Existing clients keep their current clients.assigned_to; no backfill is performed.
    CREATE TABLE IF NOT EXISTS broker_ownership_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        previous_owner_id INTEGER,
        new_owner_id INTEGER NOT NULL,
        admin_id INTEGER NOT NULL,
        reason TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE,
        FOREIGN KEY(previous_owner_id) REFERENCES users(id),
        FOREIGN KEY(new_owner_id) REFERENCES users(id),
        FOREIGN KEY(admin_id) REFERENCES users(id)
    );
    """)
    _rebuild_listings_for_manual_inventory(conn)

    # Migrate fields added in CRM and controlled-matching iterations.
    existing_users = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "must_change_password" not in existing_users:
        conn.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0")
    # Any account still using a shipped default password must change it at next login.
    for u in conn.execute("SELECT id,email,password_hash FROM users").fetchall():
        default = DEFAULT_PASSWORDS.get((u["email"] or "").lower())
        if default and check_password_hash(u["password_hash"], default):
            conn.execute("UPDATE users SET must_change_password=1 WHERE id=?", (u["id"],))

    existing_clients = {r[1] for r in conn.execute("PRAGMA table_info(clients)").fetchall()}
    for col, ddl in {
        "source":"TEXT DEFAULT ''", "temperature":"TEXT DEFAULT 'Warm'", "preferred_location":"TEXT DEFAULT ''",
        "preferred_unit_type":"TEXT DEFAULT ''", "preferred_space_min":"REAL", "preferred_space_max":"REAL",
        "bedrooms":"TEXT DEFAULT ''", "bathrooms":"TEXT DEFAULT ''", "purpose":"TEXT DEFAULT ''",
        "budget_flexibility":"TEXT DEFAULT 'Flexible'", "next_action":"TEXT DEFAULT 'Follow Up'",
        "lost_reason":"TEXT DEFAULT ''", "created_by":"INTEGER", "assigned_to":"INTEGER",
        "property_category":"TEXT DEFAULT ''", "preferred_developer":"TEXT DEFAULT ''",
        "preferred_project":"TEXT DEFAULT ''", "priority":"TEXT DEFAULT 'Normal'"
    }.items():
        if col not in existing_clients:
            conn.execute(f"ALTER TABLE clients ADD COLUMN {col} {ddl}")
    conn.execute("UPDATE clients SET assigned_to=COALESCE(assigned_to,broker_id)")
    conn.execute("UPDATE clients SET created_by=COALESCE(created_by,broker_id)")
    conn.execute("UPDATE clients SET broker_id=assigned_to WHERE assigned_to IS NOT NULL")

    # Backfill multi-location junction from legacy single preferred_location.
    for r in conn.execute("SELECT id, preferred_location FROM clients").fetchall():
        loc = (r["preferred_location"] or "").strip()
        if loc:
            try:
                conn.execute("INSERT OR IGNORE INTO client_locations(client_id, location, created_at) VALUES(?,?,?)",
                             (r["id"], loc, utc_now_naive().isoformat()))
            except Exception:
                pass

    existing_listings = {r[1] for r in conn.execute("PRAGMA table_info(listings)").fetchall()}
    for col, ddl in {
        "normalized_developer":"TEXT", "normalized_project":"TEXT", "normalized_location":"TEXT", "normalized_unit_type":"TEXT",
        "manual_json":"TEXT DEFAULT '{}'", "manual_updated_at":"TEXT", "source_type":"TEXT NOT NULL DEFAULT 'excel'",
        "manual_project_id":"INTEGER", "created_by":"INTEGER", "updated_by":"INTEGER",
        "category":"TEXT DEFAULT ''", "listing_uid":"TEXT",
        "unit_type_canonical":"TEXT"
    }.items():
        if col not in existing_listings:
            conn.execute(f"ALTER TABLE listings ADD COLUMN {col} {ddl}")

    # Backfill listing_uid for any row that does not have one yet.
    for r in conn.execute("SELECT * FROM listings WHERE listing_uid IS NULL OR listing_uid=''").fetchall():
        uid = listing_uid(r, is_db=True)
        conn.execute("UPDATE listings SET listing_uid=? WHERE id=?", (uid, r["id"]))

    # Backfill unit_type_canonical (additive; identity unaffected).
    for r in conn.execute("SELECT id, unit_type, unit_type_canonical FROM listings").fetchall():
        if (r["unit_type_canonical"] or "").strip():
            continue
        c = canonical_unit_type(r["unit_type"] or "")
        if c:
            conn.execute("UPDATE listings SET unit_type_canonical=? WHERE id=?", (c, r["id"]))

    # Targeted correction: clear canonical/category for previously-stored unknown
    # values (idempotent; does not touch raw unit_type, listing_uid, or ids).
    for r in conn.execute("SELECT id, unit_type, unit_type_canonical FROM listings").fetchall():
        if canonical_unit_type(r["unit_type"] or "") == "" and (r["unit_type_canonical"] or "").strip():
            conn.execute("UPDATE listings SET unit_type_canonical='' WHERE id=?", (r["id"],))
    for r in conn.execute("SELECT id, unit_type, category FROM listings").fetchall():
        if classify_listing_category(r["unit_type"] or "") == "" and (r["category"] or "").strip():
            conn.execute("UPDATE listings SET category='' WHERE id=?", (r["id"],))

    # Backfill listing category from unit_type when empty (derived, not invented).
    for r in conn.execute("SELECT id, unit_type, category FROM listings").fetchall():
        if (r["category"] or "").strip():
            continue
        cat = classify_listing_category(r["unit_type"] or "")
        if cat:
            conn.execute("UPDATE listings SET category=? WHERE id=?", (cat, r["id"]))

    # Rebuild normalized search/filter fields for older imports.
    rows_to_norm = conn.execute("SELECT id,developer,project,location,unit_type FROM listings WHERE normalized_location IS NULL OR normalized_location='' OR normalized_developer IS NULL OR normalized_developer='' OR normalized_project IS NULL OR normalized_project='' OR normalized_unit_type IS NULL OR normalized_unit_type=''").fetchall()
    for rr in rows_to_norm:
        conn.execute("UPDATE listings SET normalized_developer=?,normalized_project=?,normalized_location=?,normalized_unit_type=? WHERE id=?",(normalize_name(rr["developer"]),normalize_name(rr["project"]),normalize_location(rr["location"]),normalize_unit(rr["unit_type"]),rr["id"]))

    # Repair legacy price ranges stored as negative or reversed values.
    conn.execute("""
        UPDATE listings
        SET total_price_min = CASE
                WHEN total_price_min IS NULL AND total_price_max IS NULL THEN NULL
                WHEN total_price_min IS NULL THEN ABS(total_price_max)
                WHEN total_price_max IS NULL THEN ABS(total_price_min)
                ELSE MIN(ABS(total_price_min), ABS(total_price_max))
            END,
            total_price_max = CASE
                WHEN total_price_min IS NULL AND total_price_max IS NULL THEN NULL
                WHEN total_price_min IS NULL THEN ABS(total_price_max)
                WHEN total_price_max IS NULL THEN ABS(total_price_min)
                ELSE MAX(ABS(total_price_min), ABS(total_price_max))
            END
        WHERE (total_price_min IS NOT NULL AND total_price_min < 0)
           OR (total_price_max IS NOT NULL AND total_price_max < 0)
           OR (total_price_min IS NOT NULL AND total_price_max IS NOT NULL AND total_price_min > total_price_max)
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_clients_assigned_to ON clients(assigned_to)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_clients_followup ON clients(followup_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at)")
    conn.commit()

    admin = conn.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()
    if not admin:
        conn.execute(
            "INSERT INTO users(email,password_hash,role,created_at,must_change_password) VALUES(?,?,?,?,1)",
            ("admin@local", generate_password_hash("Admin123!"), "admin", utc_now_naive().isoformat())
        )
    conn.commit()
    conn.close()

def utc_now_naive():
    """Deprecated utc_now_naive() replacement: UTC-naive, matching the app's
    storage convention (timestamps stored as naive UTC ISO strings)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_now_sql():
    """UTC now as 'YYYY-MM-DD HH:MM:SS' (SQLite datetime() text format)."""
    return utc_now_naive().strftime("%Y-%m-%d %H:%M:%S")

def clean(v):
    if v is None:
        return ""
    return str(v).strip()

def norm_header(v):
    s = clean(v).lower()
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def parse_number_token(token):
    s = clean(token).lower().replace(",", "").replace(" ", "")
    s = s.replace("egp", "").replace("₤", "")
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*([km])?", s)
    if not m:
        return None
    n = float(m.group(1))
    suffix = m.group(2)
    if suffix == "m":
        n *= 1_000_000
    elif suffix == "k":
        n *= 1_000
    return n

def split_numeric_range(value, kind):
    """Parse a numeric value/range without confusing metre `m` with million `M`."""
    raw = clean(value)
    if not raw:
        return None, None, None

    low = raw.lower().strip()
    if low in {"sold", "sold out", "no info", "tba", "n/a", "na", "not available", "call for price", "hold", "by request", "-"}:
        return None, None, f'Value "{raw}" could not be parsed as a number'

    if kind == "space":
        # Main-area + garden/terrace/roof: use the first area only.
        if re.search(r"\+\s*\d+(?:\.\d+)?\s*(?:m2|m²|sqm|m)?\s*(garden|terrace|roof)", low, re.I):
            first = re.match(r"\s*(\d+(?:\.\d+)?)\s*(?:m2|m²|sqm|m)?", low, re.I)
            if first:
                n = float(first.group(1))
                return n, n, None

        # M/K in a size field means million/thousand, not metres. Keep as a
        # warning rather than silently turning 11.9M into 11.9 sqm.
        if re.search(r"\d+(?:\.\d+)?\s*[KM]\b", raw):
            return None, None, f'Value "{raw}" could not be parsed as a number'

        # Remove thousands separators in size values such as 1,200 sqm.
        low = re.sub(r"(?<=\d),(?=\d)", "", low)

        # Find numbers and optional metre units. This handles:
        # 65m-450m, 65 m - 450 m, 30m, 349-353m, 50m 105m.
        matches = list(re.finditer(
            r"(?<![A-Za-z0-9])([0-9]+(?:\.[0-9]+)?)\s*(m²|m2|sqm|m)?",
            low,
            re.I,
        ))
        nums = []
        malformed_suffix = False
        for m in matches:
            number = float(m.group(1))
            unit = (m.group(2) or "").lower()
            after = low[m.end():]
            # Ignore numeric words such as 2bed; it is not a size token.
            if not unit and re.match(r"\s*bed\b", after, re.I):
                continue
            # If a number is immediately followed by any Unicode letter and
            # there is no recognised size unit, the source is malformed.
            if not unit and re.match(r"[^\W\d_]", after, re.UNICODE):
                malformed_suffix = True
                continue
            nums.append(number)

        if malformed_suffix:
            return None, None, f'Value "{raw}" could not be parsed as a number'

        if not nums:
            return None, None, f'Value "{raw}" could not be parsed as a number'
        return min(nums), max(nums), None

    # Prices: strip currency labels, then remove thousands separators before
    # extracting numbers. A hyphen is always a range separator; prices are
    # never stored as negative.
    normalized = re.sub(r"egp|\$|\u20ac|\u00a3|usd", "", low, flags=re.I)
    normalized = re.sub(r"(?<=\d)[,\s](?=\d)", "", normalized)

    # Strict tokenization: a token is a number optionally followed by a unit
    # (k/m), and must be delimited by a separator or end-of-string. This
    # rejects malformed suffixes such as "12m2", "5MX", "abc5Mdef".
    token_re = re.compile(r"(\d+(?:\.\d+)?)\s*([kKmM]?)")
    matches = list(token_re.finditer(normalized))
    parsed = []  # list of (number, unit or None)
    pos = 0
    for m in matches:
        gap = normalized[pos:m.start()]
        if gap.strip("-\u2013\u2014, \t") != "":
            return None, None, f'Value "{raw}" could not be parsed as a number'
        unit = m.group(2).lower() if m.group(2) else None
        end = m.end()
        if end < len(normalized):
            nxt = normalized[end]
            if nxt not in " -\u2013\u2014,\t":
                return None, None, f'Value "{raw}" could not be parsed as a number'
        try:
            num = float(m.group(1))
        except ValueError:
            return None, None, f'Value "{raw}" could not be parsed as a number'
        if num < 0:
            return None, None, f'Value "{raw}" could not be parsed as a number'
        parsed.append((num, unit))
        pos = end
    if normalized[pos:].strip("-\u2013\u2014, \t") != "":
        return None, None, f'Value "{raw}" could not be parsed as a number'
    if not parsed:
        return None, None, f'Value "{raw}" could not be parsed as a number'

    # Unit resolution (deterministic):
    #   1. Explicit unit on a number always wins.
    #   2. A unit propagates only to numbers with NO explicit unit.
    #   3. A shared trailing unit applies to all unitless numbers.
    #   4. If both numbers have explicit (possibly different) units, no
    #      propagation occurs; each unit is preserved independently.
    units_present = {u for (_, u) in parsed if u is not None}
    if len(units_present) == 1:
        shared = next(iter(units_present))
        parsed = [(n, shared if u is None else u) for (n, u) in parsed]

    nums = []
    for num, unit in parsed:
        if unit == "k":
            num *= 1_000
        elif unit == "m":
            num *= 1_000_000
        nums.append(num)
    if not nums:
        return None, None, f'Value "{raw}" could not be parsed as a number'
    return min(nums), max(nums), None

def format_money(n):
    if n is None:
        return ""
    if abs(n - round(n)) < 1e-9:
        return f"{int(round(n)):,}"
    return f"{n:,.2f}".rstrip("0").rstrip(".")

def format_money_compact(n):
    if n is None:
        return ""
    n=float(n)
    if abs(n) >= 1_000_000:
        v=n/1_000_000
        text=f"{v:.1f}".rstrip("0").rstrip(".")
        return f"{text}M"
    if abs(n) >= 1_000:
        v=n/1_000
        text=f"{v:.1f}".rstrip("0").rstrip(".")
        return f"{text}K"
    return format_money(n)

def display_compact_range(a, b, suffix=""):
    if a is None and b is None:
        return ""
    if a is not None and b is not None and abs(a-b) < 1e-9:
        return format_money_compact(a) + suffix
    return f"{format_money_compact(a)} – {format_money_compact(b)}{suffix}"

def display_range(a, b, suffix=""):
    if a is None and b is None:
        return ""
    if a is not None and b is not None and abs(a-b) < 1e-9:
        return format_money(a) + suffix
    return f"{format_money(a)} – {format_money(b)}{suffix}"

def canonical_mapping(headers):
    mapping = {}
    for idx, h in enumerate(headers):
        nh = norm_header(h)
        if nh in CANON:
            mapping[CANON[nh]] = idx
    return mapping

# Controlled matching areas. Sheikh Zayed and New Zayed are intentionally separate.
# Do not collapse them into one "Zayed" bucket.
LOCATION_ALIASES = {
    "new zayed city":"New Zayed", "new zayed":"New Zayed", "new zayed city, egypt":"New Zayed",
    "shaikh zayed":"Sheikh Zayed", "sheikh zayed":"Sheikh Zayed", "zayed":"Sheikh Zayed",
    "new october":"New October", "new october city":"New October",
    "6 october":"October", "6th october":"October", "october":"October",
    "new cairo":"New Cairo", "new cairo city":"New Cairo",
    "new capital":"New Capital", "new capital city":"New Capital",
    "new heliopolis":"New Heliopolis", "al shorouk":"Al Shorouk", "shorouk":"Al Shorouk",
    "ain sokhna":"Ain Sokhna", "north coast":"North Coast", "north coast.":"North Coast",
    "hadayek october":"Hadayek October", "waslet dahshour":"Waslet Dahshour",
    "alexandria":"Alexandria", "alx":"Alexandria", "heliopolis":"Heliopolis",
    "katameya":"Katameya", "maddi":"Maadi", "maadi":"Maadi", "mehw ar":"Mehwar", "mehwar":"Mehwar",
    "sheraton":"Sheraton",
}

def normalize_text(value):
    s = re.sub(r"\s+", " ", clean(value).lower()).strip()
    return s

def normalize_location(value):
    s = normalize_text(value)
    if not s or s == "no info": return "" if not s else "No Info"
    return LOCATION_ALIASES.get(s, " ".join(w.capitalize() for w in s.split()))

def refresh_listing_location_matches():
    """Rebuild stored normalized locations after matching-area rules change.

    The raw Excel Location is never changed. This only refreshes the derived
    value used by filters/search/Smart Match so old imports receive the same
    controlled location rules as new imports.
    """
    conn = db()
    try:
        rows = conn.execute("SELECT id, location FROM listings").fetchall()
        for row in rows:
            conn.execute("UPDATE listings SET normalized_location=? WHERE id=?",
                         (normalize_location(row["location"]), row["id"]))
        conn.commit()
    finally:
        conn.close()

def normalize_name(value):
    s = normalize_text(value)
    if not s: return ""
    return " ".join(w.capitalize() for w in s.split())

def normalize_unit(value):
    s = normalize_text(value)
    # RES is the source workbook's broad residential category. Keep it distinct
    # from Apartment rather than silently treating every residential unit as a flat.
    aliases = {
        "res":"Residential", "residential":"Residential",
        "flat":"Apartment", "apartments":"Apartment", "apt":"Apartment",
        "challet":"Chalet", "chalets":"Chalet", "villas":"Villa",
        "townhouses":"Townhouse", "twin houses":"Twin House"
    }
    return aliases.get(s, " ".join(w.capitalize() for w in s.split()))


COMMERCIAL_UNIT_KEYWORDS = {"comm", "com", "commercial", "admin", "ad", "med", "medical", "ph", "retail", "ret", "office", "shop", "clinic", "warehouse", "showroom", "business"}


def _g(item, key):
    try:
        v = item.get(key)
    except AttributeError:
        v = None
    if v is None:
        try:
            v = item[key]
        except Exception:
            v = None
    return v


def listing_uid(item, is_db=False):
    """Stable logical identity for a listing (internal only)."""
    original = {}
    raw_original = _g(item, "original")
    if isinstance(raw_original, dict):
        original = raw_original
    else:
        try:
            original = json.loads(_g(item, "original_json") or "{}")
        except Exception:
            original = {}
    stable = None
    for header, value in (original or {}).items():
        h = norm_header(header)
        if h in {"project id", "unit id", "listing id", "reference id", "unit code", "listing code", "reference", "ref", "code"} and clean(value):
            stable = (h, normalize_text(value))
            break
    if stable:
        return f"stable:{stable[0]}:{stable[1]}"
    return "identity:" + "|".join([
        normalize_name(_g(item, "developer")),
        normalize_name(_g(item, "project")),
        normalize_location(_g(item, "location")),
        normalize_unit(_g(item, "unit_type")),
        str(_g(item, "space_min")),
        str(_g(item, "space_max")),
        normalize_text(_g(item, "project_location")),
        normalize_text(_g(item, "company_location")),
    ])


CANONICAL_UNIT_TYPES = (
    "Apartment", "Chalet", "Villa", "Townhouse", "Twin House",
    "Studio", "Hotel Apartment", "Commercial", "Residential",
)


def canonical_unit_type(value):
    s = normalize_text(value or "")
    low = s.lower()
    if not low:
        return ""
    if low in {"no info", "hold", "sold out", "sold", "tba", "n/a", "na", "not available", "-", "by request"}:
        return ""
    if low in ("res", "residential"):
        return "Residential"
    if low in ("apartment", "flat", "apt", "apartments"):
        return "Apartment"
    if low in ("chalet", "chalets", "challet"):
        return "Chalet"
    if low in ("villa", "villas"):
        return "Villa"
    if low in ("townhouse", "townhouses"):
        return "Townhouse"
    if low in ("twin house", "twin houses"):
        return "Twin House"
    if low in ("studio",):
        return "Studio"
    if "hotel" in low or "hotle" in low:
        return "Hotel Apartment"
    toks = set(low.replace("-", " ").split())
    if toks & COMMERCIAL_UNIT_KEYWORDS:
        return "Commercial"
    if "res" in toks:
        return "Residential"
    return ""


def classify_listing_category(unit_type):
    """Derive Residential/Commercial from a unit type. Returns '' when unknown/unreviewed."""
    c = canonical_unit_type(unit_type)
    if c in ("Residential", "Apartment", "Chalet", "Villa", "Townhouse", "Twin House", "Studio", "Hotel Apartment"):
        return "Residential"
    if c == "Commercial":
        return "Commercial"
    return ""


def client_locations_for(conn, client_id):
    rows = conn.execute("SELECT location FROM client_locations WHERE client_id=? ORDER BY location", (client_id,)).fetchall()
    return [r["location"] for r in rows]


def location_options_for_inventory(inventory):
    """Return the controlled area labels available in current broker inventory."""
    options = {
        normalize_location(item.get("location"))
        for item in inventory
        if normalize_location(item.get("location")) not in {"", "No Info"}
    }
    return sorted(options, key=str.casefold)

def parse_budget_text(value):
    """Parse client budget text, including M/K and words like million."""
    raw = clean(value)
    if not raw:
        return None, None
    low = raw.lower().replace(",", "")
    # Normalize common written multipliers before the generic parser.
    low = re.sub(r"(million|mn|mio|مليون)\b", "m", low, flags=re.I)
    low = re.sub(r"(thousand|kilo|ألف)\b", "k", low, flags=re.I)
    a,b,_ = split_numeric_range(low, "price")
    return a,b

def parse_space_text(value):
    a,b,_ = split_numeric_range(value, "space")
    return a,b


def parse_additional_fields(value):
    """Parse one additional inventory field per line: Field name: value."""
    raw = clean(value)
    result = {}
    for line_no, line in enumerate(raw.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError(f"Additional field line {line_no} must use Field name: value.")
        key, val = line.split(":", 1)
        key, val = key.strip(), val.strip()
        if not key:
            raise ValueError(f"Additional field line {line_no} needs a field name.")
        if norm_header(key) in set(CANON) | {"source", "total price", "price/m²", "space", "delivery", "finishing"}:
            raise ValueError(f'"{key}" is already a standard field. Add it in its regular input instead.')
        result[key] = val
    return result

def import_workbook(path, version_id):
    wb = load_workbook(path, data_only=False, read_only=True)
    warnings = []
    info_messages = []
    serious = []
    rows = []
    total_rows = 0

    for ws in wb.worksheets:
        values = ws.iter_rows(values_only=True)
        try:
            headers = next(values)
        except StopIteration:
            continue

        headers = list(headers)
        mapping = canonical_mapping(headers)
        if "project" not in mapping:
            serious.append(f"{ws.title}: sheet has no Project Name column")
            continue

        for excel_row, vals in enumerate(values, start=2):
            vals = list(vals)
            # Ignore fully empty trailing/formatting-only rows. They are not listings
            # and must not block publication as "missing Project Name" errors.
            if not any(v is not None and clean(v) for v in vals):
                continue
            total_rows += 1
            original = {}
            for i, h in enumerate(headers):
                if h is not None:
                    original[str(h)] = vals[i] if i < len(vals) else None

            project = clean(vals[mapping["project"]]) if mapping.get("project") is not None and mapping["project"] < len(vals) else ""
            if not project:
                serious.append(f"{ws.title}, row {excel_row}: missing Project Name")
                continue

            def get(key):
                i = mapping.get(key)
                return vals[i] if i is not None and i < len(vals) else None

            developer = clean(get("developer"))
            location = clean(get("location"))
            price_raw = clean(get("total_price"))
            m2_raw = clean(get("price_m2"))
            space_raw = clean(get("space"))

            pmin, pmax, pw = split_numeric_range(price_raw, "price")
            mmin, mmax, mw = split_numeric_range(m2_raw, "price_m2")
            smin, smax, sw = split_numeric_range(space_raw, "space")

            # Separate genuinely invalid data from normal unavailable/status values.
            unavailable = {"sold", "sold out", "no info", "tba", "n/a", "na", "not available", "call for price", "hold", "by request", "-", "launching", "lunching"}
            if price_raw == "" and mmin is not None:
                info_messages.append(f'{ws.title}, row {excel_row}: No total price (only a price per m²)')
            if price_raw and pw:
                if price_raw.lower() in unavailable:
                    info_messages.append(f'{ws.title}, row {excel_row}: Total price unavailable/status: "{price_raw}"')
                else:
                    warnings.append(f'{ws.title}, row {excel_row}: Total price "{price_raw}" could not be parsed; original text is kept')
            if m2_raw and mw:
                if m2_raw.lower() in unavailable or m2_raw.lower() in {"villa", "townhouse", "twin house", "chalet", "apartment", "admin", "res"}:
                    info_messages.append(f'{ws.title}, row {excel_row}: Price/m² is text/status: "{m2_raw}"')
                else:
                    warnings.append(f'{ws.title}, row {excel_row}: Price/m² "{m2_raw}" could not be parsed; original text is kept')
            if space_raw and sw:
                if space_raw.lower() in unavailable or re.search(r'\b(studio|bedroom|bedrooms)\b', space_raw, re.I):
                    info_messages.append(f'{ws.title}, row {excel_row}: Size is descriptive/status text: "{space_raw}"')
                else:
                    warnings.append(f'{ws.title}, row {excel_row}: Size "{space_raw}" could not be parsed; original text is kept')
            if price_raw == "" and mmin is None:
                info_messages.append(f'{ws.title}, row {excel_row}: No total price')

            rows.append({
                "source_sheet": ws.title,
                "source_row": excel_row,
                "original": original,
                "developer": developer,
                "project": project,
                "location": location,
                "price_m2_min": mmin,
                "price_m2_max": mmax,
                "total_price_min": pmin,
                "total_price_max": pmax,
                "space_min": smin,
                "space_max": smax,
                "payment_plan": clean(get("payment_plan")),
                "unit_type": clean(get("unit_type")),
                "delivery": clean(get("delivery")),
                "finishing": clean(get("finishing")),
                "maintenance": clean(get("maintenance")),
                "project_location": clean(get("project_location")),
                "company_location": clean(get("company_location")),
                "normalized_developer": normalize_name(developer),
                "normalized_project": normalize_name(project),
                "normalized_location": normalize_location(location),
                "normalized_unit_type": normalize_unit(get("unit_type")),
            })

    wb.close()
    conn = db()
    old_live = conn.execute("""SELECT source_sheet,source_row,original_json,developer,project,location,
        unit_type,space_min,space_max,project_location,company_location,manual_json,manual_updated_at
        FROM listings WHERE version_id=(SELECT id FROM versions WHERE status='live' ORDER BY id DESC LIMIT 1)
        ORDER BY source_sheet,source_row,id""").fetchall()

    # Preserve overrides by listing identity, not row number. If a real reference
    # code exists in an additional Excel column, use it; otherwise use the known
    # identity fields and pair true duplicate rows in their source order.
    from collections import defaultdict
    override_map = defaultdict(list)
    stable_id_headers = {"project id", "unit id", "listing id", "reference id", "unit code", "listing code", "reference", "ref", "code"}

    for old in old_live:
        old_manual = (old["manual_json"] or "{}").strip()
        if old_manual not in ("", "{}", "null"):
            override_map[listing_uid(old, is_db=True)].append((old_manual, old["manual_updated_at"]))

    conn.execute("DELETE FROM listings WHERE version_id=?", (version_id,))
    for r in rows:
        uid = listing_uid(r)
        candidates = override_map.get(uid, [])
        manual_json, manual_updated_at = candidates.pop(0) if candidates else ("{}", None)
        conn.execute("""INSERT INTO listings(
            version_id,source_sheet,source_row,original_json,developer,project,location,
            price_m2_min,price_m2_max,total_price_min,total_price_max,space_min,space_max,
            payment_plan,unit_type,delivery,finishing,maintenance,project_location,company_location,
            normalized_developer,normalized_project,normalized_location,normalized_unit_type,manual_json,manual_updated_at,
            listing_uid,unit_type_canonical
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            version_id,r["source_sheet"],r["source_row"],json.dumps(r["original"], ensure_ascii=False, default=str),
            r["developer"],r["project"],r["location"],r["price_m2_min"],r["price_m2_max"],
            r["total_price_min"],r["total_price_max"],r["space_min"],r["space_max"],
            r["payment_plan"],r["unit_type"],r["delivery"],r["finishing"],r["maintenance"],
            r["project_location"],r["company_location"],r["normalized_developer"],r["normalized_project"],
            r["normalized_location"],r["normalized_unit_type"],manual_json,manual_updated_at,uid,
            canonical_unit_type(r["unit_type"])
        ))
    summary = {
        "total_rows": total_rows,
        "imported_rows": len(rows),
        "rejected_rows": total_rows - len(rows),
        "warnings": len(warnings),
        "info": len(info_messages),
        "serious_errors": len(serious),
        "warning_messages": warnings[:500],
        "info_messages": info_messages[:500],
        "serious_messages": serious[:500],
    }
    conn.execute("""UPDATE versions SET total_rows=?, imported_rows=?, rejected_rows=?, warnings=?, serious_errors=?, summary_json=? WHERE id=?""",
                 (total_rows,len(rows),total_rows-len(rows),len(warnings),len(serious),json.dumps(summary,ensure_ascii=False),version_id))
    conn.commit()
    conn.close()
    return summary

VALID_ROLES = ("admin", "broker")


def load_session_user():
    """Return the active DB user identified by the session, or None.

    The session is only an identifier. Role and active status are always
    re-read from the database, so a stale session (deactivated/deleted user)
    or a tampered session role cannot grant privileges.
    """
    uid = session.get("user_id")
    if not uid:
        return None
    conn = db()
    try:
        user = conn.execute(
            "SELECT id,email,role,active,must_change_password FROM users WHERE id=?",
            (uid,),
        ).fetchone()
    finally:
        conn.close()
    if not user or not user["active"] or user["role"] not in VALID_ROLES:
        return None
    return user


def login_required(role=None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = load_session_user()
            if user is None:
                if session.get("user_id"):
                    session.clear()
                    flash("Your account is inactive. Contact the administrator.", "error")
                return redirect(url_for("login"))
            # Keep the session in sync with the authoritative DB record.
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["email"] = user["email"]
            if user["must_change_password"] and request.endpoint not in ("change_password", "logout"):
                flash("Please choose a new password before continuing.", "error")
                return redirect(url_for("change_password"))
            if role and user["role"] != role:
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return deco


def log_audit(conn, action, entity_type, entity_id=None, details=""):
    conn.execute(
        "INSERT INTO audit_logs(actor_id,action,entity_type,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
        (session.get("user_id"), action, entity_type, str(entity_id) if entity_id is not None else None,
         clean(details), utc_now_naive().isoformat())
    )


def live_version(conn):
    return conn.execute("SELECT * FROM versions WHERE status='live' ORDER BY id DESC LIMIT 1").fetchone()


def fetch_live_inventory(conn):
    """Return published Excel rows plus permanent manually-created units."""
    live = live_version(conn)
    if live:
        rows = conn.execute("""
            SELECT l.* FROM listings l
            WHERE (l.source_type='manual' AND EXISTS(SELECT 1 FROM manual_projects mp WHERE mp.id=l.manual_project_id AND mp.active=1))
               OR l.version_id=?
            ORDER BY COALESCE(l.project,''), COALESCE(l.developer,''), l.id
        """, (live["id"],)).fetchall()
    else:
        rows = conn.execute("SELECT l.* FROM listings l WHERE l.source_type='manual' AND EXISTS(SELECT 1 FROM manual_projects mp WHERE mp.id=l.manual_project_id AND mp.active=1) ORDER BY l.project,l.developer,l.id").fetchall()
    return [row_to_listing(r) for r in rows], live


def row_to_listing(row):
    d = dict(row)
    d["original"] = json.loads(d.pop("original_json", "{}") or "{}")
    manual = json.loads(d.get("manual_json") or "{}") if d.get("manual_json") else {}
    d["manual"] = manual
    d["manual_updated"] = d.get("manual_updated_at")
    excluded_original_headers = set(CANON) | {"source", "total price", "price/m²", "space", "delivery", "finishing", "maintenance"}
    additional = {k: v for k, v in d["original"].items()
                  if norm_header(k) not in excluded_original_headers and v is not None and clean(v)}
    if "_additional_fields" in manual:
        additional = manual.get("_additional_fields") or {}
    d["additional_fields"] = additional
    for k, v in manual.items():
        if k != "_history" and k in {"developer","project","location","unit_type","total_price_min","total_price_max","price_m2_min","price_m2_max","space_min","space_max","payment_plan","delivery","finishing","maintenance","project_location","company_location"}:
            d[k] = v
    d["price_display"] = display_range(d.get("total_price_min"), d.get("total_price_max"))
    d["price_display_compact"] = display_compact_range(d.get("total_price_min"), d.get("total_price_max"))
    d["m2_display"] = display_range(d.get("price_m2_min"), d.get("price_m2_max"))
    d["space_display"] = display_range(d.get("space_min"), d.get("space_max"), " m²")
    d["normalized_location"] = normalize_location(d.get("location"))
    d["normalized_developer"] = normalize_name(d.get("developer"))
    d["normalized_project"] = normalize_name(d.get("project"))
    d["normalized_unit_type"] = normalize_unit(d.get("unit_type"))
    d["display_developer"] = d.get("developer") or "Developer not specified"
    d["display_project"] = d.get("project") or "Project not specified"
    d["display_location"] = d["normalized_location"] or d.get("location") or "Location not specified"
    d["display_unit_type"] = d.get("unit_type") or "Listing"
    d["source_type"] = d.get("source_type") or "excel"
    return d


def build_project_groups(listings):
    groups = {}
    for item in listings:
        if item.get("source_type") == "manual" and item.get("manual_project_id"):
            key = ("manual", int(item["manual_project_id"]))
        else:
            key = ("excel", item.get("normalized_project") or normalize_name(item.get("project")),
                   item.get("normalized_developer") or normalize_name(item.get("developer")),
                   item.get("normalized_location") or normalize_location(item.get("location")))
        if key not in groups:
            groups[key] = {
                "key": key, "project": item.get("project") or "Project not specified",
                "developer": item.get("developer") or "Developer not specified",
                "location": item.get("normalized_location") or item.get("location") or "Location not specified",
                "manual_project_id": item.get("manual_project_id"), "unit_count": 0,
                "unit_types": set(), "size_min": None, "size_max": None,
                "price_min": None, "price_max": None, "delivery": item.get("delivery") or "",
                "source_type": item.get("source_type", "excel"), "project_location": item.get("project_location") or ""
            }
        g = groups[key]
        g["unit_count"] += 1
        if item.get("unit_type"): g["unit_types"].add(canonical_unit_type(item["unit_type"]) or item["unit_type"])
        for field, agg in (("space_min", "size_min"), ("space_max", "size_max"),
                           ("total_price_min", "price_min"), ("total_price_max", "price_max")):
            val = item.get(field)
            if val is not None:
                g[agg] = val if g[agg] is None else (min(g[agg], val) if agg.endswith("min") else max(g[agg], val))
    out=[]
    for g in groups.values():
        g["unit_types"] = sorted(g["unit_types"])
        g["unit_types_display"] = " · ".join(g["unit_types"][:4]) or "Units"
        g["size_display"] = display_range(g["size_min"], g["size_max"], " m²")
        g["price_display"] = display_compact_range(g["price_min"], g["price_max"])
        out.append(g)
    return sorted(out, key=lambda x: (x["project"].lower(), x["developer"].lower(), x["location"].lower()))

def _update_type(text):
    t = clean(text).lower()
    if any(k in t for k in ["price", "السعر", "بقى", "بدل", "million", "مليون"]): return "Price Change"
    if any(k in t for k in ["sold", "sold out", "مباع", "اتباع", "محجوز", "reserved", "reserve"]): return "Availability"
    if any(k in t for k in ["delivery", "تسليم"]): return "Delivery"
    if any(k in t for k in ["payment", "installment", "قسط", "تقسيط", "مقدم", "dp"]): return "Payment Plan"
    if any(k in t for k in ["discount", "خصم"]): return "Discount"
    if any(k in t for k in ["new unit", "new availability", "وحدة جديدة", "متاح"]): return "New Availability"
    if any(k in t for k in ["area", "space", "مساحة", "متر"]): return "Unit Specification"
    return "General Update"


def _money_numbers(text):
    out=[]
    for m in re.finditer(r'(?<!\w)(\d+(?:[\.,]\d+)?)(?:\s*)(m|million|mn|k|egp|ج|مليون)?\b', text, re.I):
        raw=m.group(0).strip()
        n=parse_number_token(raw)
        if n is not None:
            out.append((raw,n))
    return out


def analyze_update_text(source_text, inventory):
    """Create a safe, review-first WhatsApp update summary without mutating inventory.

    This intentionally treats WhatsApp text as untrusted input. It extracts likely
    project context and change lines, but never writes to listings.
    """
    projects=[]
    seen=set()
    for x in inventory:
        name=clean(x.get('project'))
        if name and normalize_name(name) not in seen:
            projects.append(name); seen.add(normalize_name(name))
    projects.sort(key=len, reverse=True)
    lines=[clean(x) for x in source_text.splitlines() if clean(x)]
    detected=[]; current_project='Unmatched / Review'
    for line in lines:
        low=normalize_name(line)
        for project in projects:
            if normalize_name(project) and normalize_name(project) in low:
                current_project=project
                break
        # Skip pure greeting/date lines unless they carry a change signal.
        typ=_update_type(line)
        signal=typ != 'General Update' or any(k in line.lower() for k in ['new','update','تحديث','بقى','بدل','available','متاح'])
        if signal:
            nums=_money_numbers(line)
            spaces=re.findall(r'(?<!\w)(\d+(?:\.\d+)?)\s*(?:m²|m2|sqm|متر|m)(?![a-z])', line, re.I)
            detected.append({
                'project': current_project,
                'type': typ,
                'source_line': line,
                'numbers': [n for _,n in nums],
                'spaces': spaces,
                'confidence': 0.92 if current_project != 'Unmatched / Review' else 0.55
            })
    grouped=[]
    by={}
    for d in detected:
        by.setdefault(d['project'], []).append(d)
    for project, items in by.items():
        grouped.append({'project':project,'updates':items})
    return {
        'title':'WhatsApp Project Update Summary',
        'source_lines':len(lines),
        'projects_affected':len(grouped),
        'updates_detected':len(detected),
        'groups':grouped,
        'note':'Review each detected change against the original WhatsApp message before editing live inventory.'
    }



def parse_project_summary(raw_text):
    """Conservative local extractor for pasted project summaries. Never invents missing values."""
    text = clean(raw_text)
    lines = [re.sub(r"\s+", " ", x).strip(" •-*\t") for x in text.splitlines() if x.strip()]
    joined = "\n".join(lines)
    result = {"project":"", "developer":"", "location":"", "project_location":"", "company_location":"",
              "description":"", "delivery":"", "finishing":"", "maintenance":"", "payment_plan":"",
              "bedrooms":"", "units":[], "source_text":text}

    # Project/developer: explicit labels first, then a common "Project by Developer" heading.
    for line in lines:
        m = re.match(r"(?i)(?:project(?: name)?|project)\s*[:：-]\s*(.+)", line)
        if m and not result["project"]: result["project"] = m.group(1).strip()
        m = re.match(r"(?i)developer\s*[:：-]\s*(.+)", line)
        if m and not result["developer"]: result["developer"] = m.group(1).strip()
    if not result["project"] and lines:
        head = lines[0]
        m = re.match(r"(.+?)\s+(?:by|developed by)\s+(.+)", head, re.I)
        if m:
            result["project"], result["developer"] = m.group(1).strip(), m.group(2).strip()
        elif not re.search(r"\d", head) and len(head) < 90 and not re.search(r"(?i)location|delivery|payment|developer", head):
            result["project"] = head

    patterns = {
        "location": [r"(?i)(?:location|area|destination)\s*[:：-]\s*(.+)"],
        "project_location": [r"(?i)(?:address|project location|road|km\s*\d+[^,]*)\s*[:：-]\s*(.+)"],
        "company_location": [r"(?i)(?:company location|developer location|hq)\s*[:：-]\s*(.+)"],
        "delivery": [r"(?i)(?:delivery|deliver(?:y date)?|handover)\s*[:：-]?\s*(?:in|by)?\s*(20\d{2}|ready to move|\d+\s*months?)"],
        "finishing": [r"(?i)(fully finished(?:\s+and\s+furnished)?|semi[- ]finished|core\s*&\s*shell|finished|furnished)"],
        "maintenance": [r"(?i)maintenance\s*[:：-]?\s*(\d+(?:\.\d+)?\s*%?)"],
        "bedrooms": [r"(?i)(\d+)\s*(?:bedrooms?|beds?)"],
    }
    for field, pats in patterns.items():
        for pat in pats:
            m = re.search(pat, joined)
            if m:
                result[field] = (m.group(1) if m.lastindex else m.group(0)).strip()
                break
    if not result["location"]:
        for line in lines:
            area_match = re.search(r"(?i)\b(ain sokhna|sokhna|new cairo|east cairo|west cairo|new capital|sheikh zayed|new zayed|6th of october|north coast|ras el hekma|alexandria)\b", line)
            if area_match:
                result["location"] = area_match.group(1).title()
                if "," in line: result["project_location"] = line
                break
    pay_lines=[]
    for line in lines:
        if re.search(r"(?i)down payment|\bDP\b|installment|payment plan|\d+\s*years?", line):
            pay_lines.append(line)
    if pay_lines: result["payment_plan"] = " | ".join(dict.fromkeys(pay_lines))

    # Unit rows: require both a recognizable area and a price, so unrelated numbers are not turned into inventory.
    for line in lines:
        area = re.search(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(?:m²|m2|sqm|m)\b", line, re.I)
        price = re.search(r"(?<![\w.])(\d+(?:\.\d+)?)\s*([kK]|M)\b", line)
        pm2 = re.search(r"(?i)(?:price\s*(?:/|per)\s*m(?:²|2)?|m(?:²|2)\s*price)\s*[:：-]?\s*([\d,.]+(?:\s*[kKmM])?)", line)
        if not area or not price: continue
        unit_type = "Apartment"
        tm = re.search(r"(?i)\b(studio|apartment|chalet|villa|townhouse|twin house|duplex|commercial|office)\b", line)
        if tm: unit_type = tm.group(1).title()
        outdoor = ""
        om = re.search(r"(?i)\b(garden|roof|terrace)\b", line)
        if om: outdoor = om.group(1).title()
        beds = ""
        bm = re.search(r"(?i)(\d+)\s*(?:bedrooms?|beds?)", line)
        if bm: beds = bm.group(1)
        elif result["bedrooms"]: beds = result["bedrooms"]
        additional = []
        if outdoor: additional.append(f"Outdoor: {outdoor}")
        if beds: additional.append(f"Bedrooms: {beds}")
        result["units"].append({"unit_type":unit_type,"space":area.group(1),"total_price":price.group(0).replace(" ",""),
                                "price_m2":(pm2.group(1).replace(" ","") if pm2 else ""),"payment_plan":result["payment_plan"],"delivery":result["delivery"],
                                "finishing":result["finishing"],"maintenance":result["maintenance"],
                                "additional_fields":"\n".join(additional),"source_line":line})
    # Keep original wording as description context when no separate description exists.
    result["description"] = "Imported from pasted summary; verify all extracted fields against the source."
    return result

def update_summary_text(summary):
    lines=['TODAY\'S PROJECT UPDATES','']
    for idx,g in enumerate(summary.get('groups',[]),1):
        lines += [f"{idx:02d} — {g['project']}"]
        for u in g.get('updates',[]):
            line=f"- {u['type']}: {u['source_line']}"
            lines.append(line)
        lines.append('')
    if not summary.get('groups'):
        lines.append('No clear project updates were detected. Review the pasted messages manually.')
    return '\n'.join(lines).strip()


@app.route('/admin/update-intelligence', methods=['GET','POST'])
@login_required('admin')
def update_intelligence():
    conn=db()
    inventory,_=fetch_live_inventory(conn)
    if request.method=='POST':
        source_text=clean(request.form.get('source_text'))
        if not source_text:
            conn.close(); flash('Paste the WhatsApp messages first.','error')
            return redirect(url_for('update_intelligence'))
        summary=analyze_update_text(source_text, inventory)
        now=utc_now_naive().isoformat()
        cur=conn.execute('INSERT INTO update_intelligence(source_text,summary_json,created_by,created_at) VALUES(?,?,?,?)',
                          (source_text,json.dumps(summary,ensure_ascii=False),session.get('user_id'),now))
        conn.execute('INSERT INTO audit_logs(actor_id,action,entity_type,entity_id,details,created_at) VALUES(?,?,?,?,?,?)',
                     (session.get('user_id'),'UPDATE_INTELLIGENCE_ANALYZED','update_intelligence',str(cur.lastrowid),
                      json.dumps({'updates_detected':summary['updates_detected'],'projects_affected':summary['projects_affected']}),now))
        conn.commit(); conn.close()
        return render_template('update_intelligence.html', inventory=inventory, summary=summary,
                               summary_text=update_summary_text(summary), source_text=source_text, history=[])
    history=conn.execute('SELECT ui.*,u.email AS creator FROM update_intelligence ui LEFT JOIN users u ON u.id=ui.created_by ORDER BY ui.id DESC LIMIT 12').fetchall()
    conn.close()
    return render_template('update_intelligence.html',inventory=inventory,summary=None,summary_text='',source_text='',history=history)


def _broker_sales_target():
    """Sales target in EGP; configurable via BROKER_PORTAL_SALES_TARGET (default 10,000,000)."""
    raw = os.environ.get("BROKER_PORTAL_SALES_TARGET")
    if raw and raw.strip():
        n = parse_number_token(raw)
        if n and n > 0:
            return n
    return 10_000_000


@app.route("/dashboard")
@login_required()
def dashboard():
    conn = db()
    inventory, live = fetch_live_inventory(conn)
    groups = build_project_groups(inventory)
    stats = {
        "projects": len(groups), "listings": len(inventory),
        "warnings": (live["warnings"] if live else 0) or 0,
        "last_upload": live["created_at"] if live else "—",
        "last_status": live["status"] if live else "No Excel version"
    }

    # Use the project's established model: followup_at is stored as naive UTC;
    # Cairo-local boundaries are computed with cairo_day_utc_bounds().
    today = cairo_now().strftime("%Y-%m-%d")
    day_start, day_end = cairo_day_utc_bounds(today)
    now_utc = utc_now_sql()
    scope = "" if session.get("role") == "admin" else " AND c.assigned_to=?"
    scope_args = () if session.get("role") == "admin" else (session["user_id"],)
    clients_total = conn.execute("SELECT COUNT(*) AS n FROM clients c WHERE 1=1" + scope, scope_args).fetchone()["n"]
    followups_today = conn.execute(
        "SELECT COUNT(*) AS n FROM clients c WHERE c.followup_at IS NOT NULL AND c.followup_at >= ? AND c.followup_at < ? AND c.status NOT IN ('Closed','Not Interested')" + scope,
        (day_start, day_end) + scope_args
    ).fetchone()["n"]
    open_clients = conn.execute("SELECT COUNT(*) AS n FROM clients c WHERE c.status NOT IN ('Closed','Not Interested')" + scope, scope_args).fetchone()["n"]
    base = "SELECT c.*, owner.email AS broker_email, creator.email AS creator_email FROM clients c LEFT JOIN users owner ON owner.id=c.assigned_to LEFT JOIN users creator ON creator.id=c.created_by"
    due_clients = conn.execute(base + " WHERE c.followup_at IS NOT NULL AND datetime(c.followup_at)<=? AND c.status NOT IN ('Closed','Not Interested')" + scope + " ORDER BY datetime(c.followup_at) ASC LIMIT 8", (now_utc,) + scope_args).fetchall()
    upcoming_clients = conn.execute(base + " WHERE c.followup_at IS NOT NULL AND c.followup_at >= ? AND c.followup_at < ? AND datetime(c.followup_at)>? AND c.status NOT IN ('Closed','Not Interested')" + scope + " ORDER BY datetime(c.followup_at) ASC LIMIT 6", (day_start, day_end, now_utc) + scope_args).fetchall()
    recent_clients = conn.execute(base + (" WHERE c.assigned_to=?" if scope else "") + " ORDER BY c.id DESC LIMIT 6", scope_args).fetchall()
    favorite_count = conn.execute("SELECT COUNT(*) AS n FROM favorites WHERE user_id=?", (session["user_id"],)).fetchone()["n"]
    opp_scope = "" if session.get("role") == "admin" else " AND c.assigned_to=?"
    opp_args = () if session.get("role") == "admin" else (session["user_id"],)
    pipeline = {}
    pipeline["Hot"] = conn.execute("SELECT COUNT(*) AS n FROM clients c WHERE c.temperature='Hot' AND c.status NOT IN ('Closed','Not Interested')" + scope, scope_args).fetchone()["n"]
    pipeline["Viewing"] = conn.execute("SELECT COUNT(*) AS n FROM clients c WHERE c.status='Viewing'" + scope, scope_args).fetchone()["n"]
    pipeline["Negotiation"] = conn.execute("SELECT COUNT(*) AS n FROM clients c WHERE c.status='Negotiation'" + scope, scope_args).fetchone()["n"]
    month_prefix=cairo_now().strftime("%Y-%m")
    won_rows = conn.execute("SELECT o.offered_price, o.updated_at, o.created_at FROM opportunities o JOIN clients c ON c.id=o.client_id WHERE o.status='Won'" + opp_scope, opp_args).fetchall()
    def _in_cairo_month(r):
        ts = r["updated_at"] or r["created_at"]
        if not ts:
            return False
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", ""))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(CAIRO_TZ).strftime("%Y-%m") == month_prefix
        except Exception:
            return False
    won_rows = [r for r in won_rows if _in_cairo_month(r)]
    def _money(v):
        if v is None: return 0.0
        a, b = parse_budget_text(v)
        if a is not None:
            return float(a)
        n = parse_number_token(v)
        if n is not None:
            return float(n)
        # Fallback: extract any numeric token.
        nums=re.findall(r"\d+(?:\.\d+)?", str(v).replace(",", ""))
        return float(nums[0]) if nums else 0.0
    sales_value=sum(_money(r["offered_price"]) for r in won_rows)
    target=_broker_sales_target()
    target_pct=min(100, round((sales_value/target)*100)) if target else 0
    conn.close()
    stats["sales_value"] = sales_value; stats["target"] = target; stats["target_pct"] = target_pct; stats["pipeline"] = pipeline
    return render_template("dashboard.html", stats=stats, clients_total=clients_total,
                           followups_today=followups_today, open_clients=open_clients,
                           due_clients=due_clients, upcoming_clients=upcoming_clients,
                           recent_clients=recent_clients, favorite_count=favorite_count)

@app.route("/")
def index():
    if not load_session_user():
        if session.get("user_id"):
            session.clear()
        return redirect(url_for("login"))
    return redirect(url_for("projects"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = clean(request.form.get("email")).lower()
        password = request.form.get("password","")
        if login_locked(email):
            flash("Too many failed attempts. Try again in 15 minutes.", "error")
            return render_template("login.html"), 429
        conn=db()
        user=conn.execute("SELECT * FROM users WHERE lower(email)=? AND active=1",(email,)).fetchone()
        conn.close()
        if user and user["role"] in VALID_ROLES and check_password_hash(user["password_hash"],password):
            login_succeeded(email)
            session.clear()
            session.permanent=True
            session["user_id"]=user["id"]; session["role"]=user["role"]; session["email"]=user["email"]
            return redirect(url_for("dashboard"))
        login_failed(email)
        flash("Invalid email or password.", "error")
    return render_template("login.html")

@app.route("/account/password", methods=["GET", "POST"])
@login_required()
def change_password():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        conn = db()
        user = conn.execute("SELECT password_hash FROM users WHERE id=?", (session["user_id"],)).fetchone()
        if not user or not check_password_hash(user["password_hash"], current):
            flash("Current password is incorrect.", "error")
        elif len(new_password) < 10:
            flash("Choose a password with at least 10 characters.", "error")
        elif new_password != confirm:
            flash("The new passwords do not match.", "error")
        elif new_password == current or new_password in DEFAULT_PASSWORDS.values():
            flash("Choose a different password from the current/default one.", "error")
        else:
            conn.execute("UPDATE users SET password_hash=?, must_change_password=0 WHERE id=?", (generate_password_hash(new_password), session["user_id"]))
            log_audit(conn, "Changed own password", "user", session["user_id"])
            conn.commit()
            flash("Your password has been updated.", "success")
        conn.close()
    return render_template("change_password.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/projects")
@login_required()
def projects():
    conn = db()
    inventory, live = fetch_live_inventory(conn)
    q = normalize_text(request.args.get("q"))
    developer = clean(request.args.get("developer"))
    location = clean(request.args.get("location"))
    unit_type = clean(request.args.get("unit_type"))
    project = clean(request.args.get("project"))
    total_min = request.args.get("total_min", type=float)
    total_max = request.args.get("total_max", type=float)
    m2_min = request.args.get("m2_min", type=float)
    m2_max = request.args.get("m2_max", type=float)
    space_min = request.args.get("space_min", type=float)
    space_max = request.args.get("space_max", type=float)
    favs = {r[0] for r in conn.execute("SELECT listing_id FROM favorites WHERE user_id=?", (session["user_id"],)).fetchall()}
    filtered = []
    for item in inventory:
        hay = " ".join([item.get(k) or "" for k in ["developer","project","location","unit_type","normalized_location","normalized_developer","normalized_project","normalized_unit_type"]]).lower()
        if q and q not in hay: continue
        if developer and item["normalized_developer"] != normalize_name(developer): continue
        if location and item["normalized_location"] != normalize_location(location): continue
        if project and item["normalized_project"] != normalize_name(project): continue
        if unit_type and (item.get("unit_type_canonical") or canonical_unit_type(item.get("unit_type"))) != canonical_unit_type(unit_type): continue
        if total_min is not None:
            hi=item["total_price_max"] if item["total_price_max"] is not None else item["total_price_min"]
            if hi is None or hi < total_min: continue
        if total_max is not None:
            lo=item["total_price_min"] if item["total_price_min"] is not None else item["total_price_max"]
            if lo is None or lo > total_max: continue
        if m2_min is not None:
            hi=item["price_m2_max"] if item["price_m2_max"] is not None else item["price_m2_min"]
            if hi is None or hi < m2_min: continue
        if m2_max is not None:
            lo=item["price_m2_min"] if item["price_m2_min"] is not None else item["price_m2_max"]
            if lo is None or lo > m2_max: continue
        if space_min is not None:
            hi=item["space_max"] if item["space_max"] is not None else item["space_min"]
            if hi is None or hi < space_min: continue
        if space_max is not None:
            lo=item["space_min"] if item["space_min"] is not None else item["space_max"]
            if lo is None or lo > space_max: continue
        item["favorite"] = item["id"] in favs
        filtered.append(item)
    groups = build_project_groups(filtered)
    page = max(1, request.args.get("page", 1, type=int))
    per_page = 24
    total_groups = len(groups)
    total_pages = max(1, (total_groups + per_page - 1) // per_page)
    page = min(page, total_pages)
    paged_groups = groups[(page-1)*per_page:page*per_page]
    all_groups = build_project_groups(inventory)
    filters = {
        "developers": sorted({x["normalized_developer"] for x in inventory if x["normalized_developer"]}),
        "locations": sorted({x["normalized_location"] for x in inventory if x["normalized_location"]}),
        "projects": sorted({x["normalized_project"] for x in inventory if x["normalized_project"]}),
        "unit_types": sorted({x.get("unit_type_canonical") or canonical_unit_type(x.get("unit_type")) for x in inventory if x.get("unit_type")}),
    }
    conn.close()
    return render_template("projects.html", projects=paged_groups, live=live, filters=filters, listing_count=len(filtered), page=page, total_pages=total_pages, total_projects=total_groups)


@app.route("/project")
@login_required()
def project_detail():
    conn=db()
    manual_id=request.args.get("manual_project_id",type=int)
    inventory, live=fetch_live_inventory(conn)
    project_record=None
    if manual_id:
        project_record=conn.execute("SELECT * FROM manual_projects WHERE id=? AND active=1",(manual_id,)).fetchone()
        if not project_record:
            conn.close(); abort(404)
        units=[x for x in inventory if x.get("source_type")=="manual" and x.get("manual_project_id")==manual_id]
    else:
        project_name=clean(request.args.get("project")); developer=clean(request.args.get("developer")); location=clean(request.args.get("location"))
        if not project_name:
            conn.close(); abort(404)
        pkey=(normalize_name(project_name),normalize_name(developer),normalize_location(location))
        units=[x for x in inventory if (x.get("normalized_project"),x.get("normalized_developer"),x.get("normalized_location"))==pkey and x.get("source_type")!="manual"]
        project_record={"project":project_name,"developer":developer,"location":location,"description":"","project_location":"","company_location":""}
    conn.close()
    if not units and not project_record:
        abort(404)
    unit_types=sorted({x.get("unit_type") for x in units if x.get("unit_type")})
    return render_template("project_detail.html", project=project_record, units=units, unit_types=unit_types, manual_id=manual_id)

@app.route("/listing/<int:listing_id>/favorite", methods=["POST"])
@login_required()
def toggle_favorite(listing_id):
    conn = db()
    visible = conn.execute("""SELECT l.id FROM listings l LEFT JOIN versions v ON v.id=l.version_id
        WHERE l.id=? AND ((l.source_type='manual' AND EXISTS(SELECT 1 FROM manual_projects mp WHERE mp.id=l.manual_project_id AND mp.active=1)) OR v.status='live')""",(listing_id,)).fetchone()
    if not visible:
        conn.close(); abort(404)
    exists = conn.execute("SELECT id FROM favorites WHERE user_id=? AND listing_id=?", (session["user_id"], listing_id)).fetchone()
    if exists:
        conn.execute("DELETE FROM favorites WHERE id=?", (exists["id"],))
        state = False
    else:
        conn.execute("INSERT OR IGNORE INTO favorites(user_id,listing_id,created_at) VALUES(?,?,?)", (session["user_id"], listing_id, utc_now_naive().isoformat()))
        state = True
    conn.commit(); conn.close()
    return jsonify({"favorite": state})

@app.route("/listing/<int:listing_id>")
@login_required()
def listing_detail(listing_id):
    conn = db()
    r = conn.execute("""SELECT l.* FROM listings l LEFT JOIN versions v ON v.id=l.version_id
                      WHERE l.id=? AND ((l.source_type='manual' AND EXISTS(SELECT 1 FROM manual_projects mp WHERE mp.id=l.manual_project_id AND mp.active=1)) OR v.status='live')""", (listing_id,)).fetchone()
    if not r:
        conn.close(); abort(404)
    listing = row_to_listing(r)
    listing['favorite'] = bool(conn.execute("SELECT 1 FROM favorites WHERE user_id=? AND listing_id=?", (session['user_id'], listing_id)).fetchone())
    if listing.get("manual_project_id"):
        listing["manual_project"] = conn.execute("SELECT * FROM manual_projects WHERE id=?",(listing["manual_project_id"],)).fetchone()
    if session.get("role") == "admin":
        available_clients = conn.execute("SELECT id,name,phone FROM clients ORDER BY id DESC LIMIT 500").fetchall()
    else:
        available_clients = conn.execute("SELECT id,name,phone FROM clients WHERE assigned_to=? ORDER BY id DESC LIMIT 500", (session["user_id"],)).fetchall()
    conn.close()
    wa_text = (
        f"Project: {listing['project']}\n"
        f"Developer: {listing['developer']}\n"
        f"Location: {listing['location']}\n"
        f"Unit: {listing['unit_type']}\n"
        f"Size: {listing['space_display']}\n"
        f"Total Price: {listing['price_display']}\n"
        f"Payment Plan: {listing['payment_plan']}\n"
        f"Delivery: {listing['delivery']}"
    )
    return render_template("listing.html", listing=listing, wa_text=wa_text, available_clients=available_clients)

@app.route("/listing/<int:listing_id>/offer-to-client", methods=["POST"])
@login_required()
def offer_listing_to_client(listing_id):
    client_id = request.form.get("client_id", type=int)
    if not client_id:
        flash("Choose a client first.", "error")
        return redirect(url_for("listing_detail", listing_id=listing_id))
    conn = db()
    listing = conn.execute("""SELECT l.* FROM listings l LEFT JOIN versions v ON v.id=l.version_id
        WHERE l.id=? AND ((l.source_type='manual' AND EXISTS(
            SELECT 1 FROM manual_projects mp WHERE mp.id=l.manual_project_id AND mp.active=1
        )) OR (l.source_type!='manual' AND v.status='live'))""", (listing_id,)).fetchone()
    client_scope = "" if session.get("role") == "admin" else " AND assigned_to=?"
    args = (client_id,) if session.get("role") == "admin" else (client_id, session["user_id"])
    client = conn.execute("SELECT * FROM clients WHERE id=?" + client_scope, args).fetchone()
    if not listing or not client:
        conn.close()
        abort(404)
    now = utc_now_naive().isoformat()
    project = listing["project"] or "Property"
    offered = request.form.get("offered_price") or display_range(listing["total_price_min"], listing["total_price_max"])
    cur = conn.execute("""INSERT INTO opportunities(client_id,listing_id,project,offered_price,status,temperature,notes,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?)""", (client_id, listing_id, project, offered, "New", client["temperature"] or "Warm", clean(request.form.get("notes")), now, now))
    conn.execute("INSERT INTO activities(client_id,opportunity_id,activity_type,body,created_at,created_by) VALUES(?,?,?,?,?,?)",
                 (client_id, cur.lastrowid, "Offer", f"Added unit from inventory: {project} · {offered or 'Price not set'}", now, session["user_id"]))
    log_audit(conn, "Added inventory unit to client", "opportunity", cur.lastrowid, f"Client {client_id}; Listing {listing_id}")
    conn.commit()
    conn.close()
    flash("Unit added to the client's opportunities.", "success")
    return redirect(url_for("client_detail", client_id=client_id))


@app.route("/listing/<int:listing_id>/edit", methods=["GET", "POST"])
@login_required("admin")
def edit_listing(listing_id):
    conn = db()
    r = conn.execute("SELECT l.* FROM listings l LEFT JOIN versions v ON v.id=l.version_id WHERE l.id=? AND (l.source_type='manual' OR v.status='live')", (listing_id,)).fetchone()
    if not r:
        conn.close()
        abort(404)
    listing = row_to_listing(r)
    if request.method == "POST":
        f = request.form
        text_fields = ["developer","project","location","unit_type","payment_plan","delivery","finishing","maintenance","project_location","company_location"]
        numeric_fields = ["total_price_min","total_price_max","price_m2_min","price_m2_max","space_min","space_max"]
        fields = text_fields + numeric_fields
        manual = json.loads(r["manual_json"] or "{}")
        history = manual.get("_history", [])
        changes = {}
        new_manual = dict(manual)
        for field in fields:
            if field not in f:
                continue
            raw = f.get(field, "").strip()
            if field in numeric_fields:
                if raw == "":
                    new_value = None
                else:
                    try:
                        new_value = float(raw)
                        if new_value < 0:
                            raise ValueError
                    except ValueError:
                        flash(f"Invalid value for {field.replace('_',' ')}.", "error")
                        conn.close()
                        return redirect(url_for("edit_listing", listing_id=listing_id))
            else:
                new_value = raw
            old_value = row_to_listing(r).get(field)
            if old_value != new_value:
                changes[field] = {"old": old_value, "new": new_value}
                new_manual[field] = new_value
        for minimum, maximum, label in (("total_price_min", "total_price_max", "total price"),
                                        ("price_m2_min", "price_m2_max", "price per m²"),
                                        ("space_min", "space_max", "space")):
            low_value = new_manual.get(minimum, r[minimum])
            high_value = new_manual.get(maximum, r[maximum])
            if low_value is not None and high_value is not None and low_value > high_value:
                flash(f"The minimum {label} cannot be greater than the maximum.", "error")
                conn.close()
                return redirect(url_for("edit_listing", listing_id=listing_id))
        if "additional_fields" in f:
            try:
                new_additional = parse_additional_fields(f.get("additional_fields", ""))
            except ValueError as exc:
                flash(str(exc), "error")
                conn.close()
                return redirect(url_for("edit_listing", listing_id=listing_id))
            old_additional = row_to_listing(r).get("additional_fields", {})
            if old_additional != new_additional:
                changes["additional_fields"] = {"old": old_additional, "new": new_additional}
                new_manual["_additional_fields"] = new_additional
        if changes:
            now = utc_now_naive().isoformat()
            history.append({"by": session.get("email", "Admin"), "at": now, "fields": changes})
            new_manual["_history"] = history[-50:]
            conn.execute("UPDATE listings SET manual_json=?, manual_updated_at=?, updated_by=? WHERE id=?", (json.dumps(new_manual, ensure_ascii=False), now, session["user_id"], listing_id))
            log_audit(conn, "Updated listing values", "listing", listing_id, json.dumps(changes, ensure_ascii=False, default=str))
            conn.commit()
            flash(f"Saved {len(changes)} manual override(s).", "success")
        else:
            flash("No changes to save.", "success")
        manual_project_id = r["manual_project_id"] if r["source_type"] == "manual" else None
        conn.close()
        if manual_project_id:
            return redirect(url_for("admin_manual_project", project_id=manual_project_id))
        return redirect(url_for("listing_detail", listing_id=listing_id))
    manual_project_id = listing.get("manual_project_id") if listing.get("source_type") == "manual" else None
    conn.close()
    return render_template("listing_edit.html", listing=listing, manual_project_id=manual_project_id)

@app.route("/listing/<int:listing_id>/reset-override", methods=["POST"])
@login_required("admin")
def reset_listing_override(listing_id):
    field = clean(request.form.get("field"))
    allowed = {"developer","project","location","unit_type","total_price_min","total_price_max","price_m2_min","price_m2_max","space_min","space_max","payment_plan","delivery","finishing","maintenance","project_location","company_location"}
    if field not in allowed:
        abort(400)
    conn = db()
    r = conn.execute("SELECT l.* FROM listings l LEFT JOIN versions v ON v.id=l.version_id WHERE l.id=? AND (l.source_type='manual' OR v.status='live')", (listing_id,)).fetchone()
    if not r:
        conn.close()
        abort(404)
    manual = json.loads(r["manual_json"] or "{}")
    if field in manual:
        old_value = manual.get(field)
        original = json.loads(r["original_json"] or "{}")
        original_map = {
            "developer":"Developer Name", "project":"Project Name", "location":"Location",
            "unit_type":"unit type", "payment_plan":"payment plan", "delivery":"Dlivery date",
            "finishing":"Finshing", "maintenance":"Maintenance", "project_location":"Porject Location",
            "company_location":"Compeny loction"
        }
        raw_original = original.get(original_map.get(field, ""), None)
        if field in {"total_price_min","total_price_max","price_m2_min","price_m2_max","space_min","space_max"}:
            original_value = r[field]
        else:
            original_value = r[field]
        history = manual.get("_history", [])
        history.append({"by": session.get("email", "Admin"), "at": utc_now_naive().isoformat(), "fields": {field: {"old": old_value, "new": original_value, "action": "reset"}}})
        del manual[field]
        manual["_history"] = history[-50:]
        conn.execute("UPDATE listings SET manual_json=?, manual_updated_at=?, updated_by=? WHERE id=?", (json.dumps(manual, ensure_ascii=False), utc_now_naive().isoformat(), session["user_id"], listing_id))
        log_audit(conn, "Reset listing override", "listing", listing_id, field)
        conn.commit()
        flash(f"Reset {field.replace('_',' ')} to the Excel value.", "success")
    manual_project_id = r["manual_project_id"] if r["source_type"] == "manual" else None
    conn.close()
    if manual_project_id:
        return redirect(url_for("admin_manual_project", project_id=manual_project_id))
    return redirect(url_for("edit_listing", listing_id=listing_id))

def client_scope_sql():
    if session.get("role") == "admin": return "", ()
    return " AND c.assigned_to=?", (session["user_id"],)


def get_client_or_404(client_id):
    conn=db()
    extra="" if session.get("role")=="admin" else " AND c.assigned_to=?"
    args=(client_id,) if session.get("role")=="admin" else (client_id,session["user_id"])
    c=conn.execute("""SELECT c.*, owner.email AS broker_email, owner.role AS owner_role, creator.email AS creator_email
        FROM clients c LEFT JOIN users owner ON owner.id=c.assigned_to
        LEFT JOIN users creator ON creator.id=c.created_by
        WHERE c.id=?"""+extra,args).fetchone()
    if not c:
        conn.close(); abort(404)
    return conn,c

# Budget matching policy (percentage-based, defensible):
#   - Exact/best: property starting price <= stated budget.
#   - Near-budget (alternative): stated budget < starting price <= stated budget * (1 + NEAR_BUDGET_PCT).
#   - Excluded: starting price > stated budget * (1 + NEAR_BUDGET_PCT).
#   - Lower window bound: stated budget * BUDGET_LOWER_PCT (properties far below budget are excluded).
# Percentages keep the tolerance proportional across price levels (2M, 5M, 10M, ...).
BUDGET_NEAR_PCT = 0.10   # near-budget band: up to 10% above the stated budget
BUDGET_LOWER_PCT = 0.60  # lower window bound: 60% of the stated budget


def recommendation_window_for(client):
    """(low, high, stated_budget_top).

    low  = stated budget * BUDGET_LOWER_PCT  (60%)
    high = stated budget * (1 + BUDGET_NEAR_PCT)  (110%)
    stated_budget_top = the client's stated top budget.
    """
    bmin,bmax=parse_budget_text(client["budget"] or "")
    if bmin is None and bmax is None:
        return None
    top=bmax if bmax is not None else bmin
    bottom=bmin if bmin is not None else bmax
    low = max(0.0, bottom * BUDGET_LOWER_PCT)
    high = top * (1.0 + BUDGET_NEAR_PCT)
    return (low, high, top)


def recommendation_score(client, listing, recommendation_window=None):
    """Score a unit as Best Match, Good Alternative, Near-Budget or Stretch.

    Controlled areas stay strict: New Zayed is never treated as Sheikh Zayed.
    Budget uses the project's starting price and range against the client's
    budget window; wide ranges stay in the results (capped at Good Alternative
    when only the range, not the starting price, reaches the budget).
    """
    score=0
    reasons=[]
    band="stretch"
    cap_alternative=False
    budget_fits=False
    pmin=None; pmax=None; stated_top=None; low=None; high=None

    # Multiple preferred locations: a unit matches if its area is in the client's set.
    locs = client.get("preferred_locations_list") if isinstance(client, dict) else None
    if not locs:
        single = client["preferred_location"] if "preferred_location" in client.keys() else ""
        locs = [single] if (single or "").strip() else []
    norm_locs = [normalize_location(x) for x in (locs or []) if (x or "").strip()]
    norm_locs = [x for x in norm_locs if x and x != "No Info"]
    listing_location = normalize_location(listing.get("location") or "")
    if not norm_locs:
        # Missing location information must not count as a successful location match.
        return 0, [], "", False, False
    if not listing_location or listing_location not in norm_locs:
        return 0, [], "", False, False
    if len(norm_locs) == 1:
        score += 30
        reasons.append(f"Preferred area: {listing_location}")
    else:
        score += 30
        reasons.append(f"Preferred area: {listing_location} (one of {len(norm_locs)} selected)")
    # Property category (Residential/Commercial) filter.
    client_cat = (client.get("property_category") if isinstance(client, dict) else client["property_category"]) if ("property_category" in (client.keys() if hasattr(client, "keys") else [])) else ""
    client_cat = (client_cat or "").strip()
    listing_cat = (listing.get("category") or "").strip() or classify_listing_category(listing.get("unit_type"))
    if client_cat:
        if not listing_cat or listing_cat != client_cat:
            return 0, [], "", False, False
        score += 8
        reasons.append(f"Category: {client_cat}")
    elif not listing_cat:
        reasons.append("Category not classified")
    # Preferred developer / project (soft boosts).
    pref_dev = (client.get("preferred_developer") if isinstance(client, dict) else "") or ""
    if pref_dev and normalize_name(pref_dev) == normalize_name(listing.get("developer") or ""):
        score += 6
        reasons.append(f"Preferred developer: {pref_dev}")
    pref_proj = (client.get("preferred_project") if isinstance(client, dict) else "") or ""
    if pref_proj and normalize_name(pref_proj) == normalize_name(listing.get("project") or ""):
        score += 6
        reasons.append(f"Preferred project: {pref_proj}")

    if recommendation_window:
        low,high=recommendation_window[0],recommendation_window[1]
        stated_top=recommendation_window[2] if len(recommendation_window)>2 else high
        pmin=listing.get("total_price_min")
        pmax=listing.get("total_price_max")
        if pmin is None and pmax is None:
            return 0, [], "", False, False
        pmin=pmin if pmin is not None else pmax
        pmax=pmax if pmax is not None else pmin
        if pmin > pmax:
            pmin,pmax=pmax,pmin
        wide = pmin > 0 and pmax / pmin > 3.0
        # Projects are sold "starting from X": a wide range (e.g. 7.8M–61M) is NOT excluded.
        # What matters is whether the starting price (or the range) reaches the client's budget window.
        # Hard cap: listing is excluded unless the whole range is within the
        # approved budget window [60% of budget, 110% of budget].
        if pmax < low or pmin > high:
            return 0, [], "", False, False
        if low <= pmin <= high:
            budget_fits=True
            over_stated = pmin > stated_top   # starts above the budget the client actually said (within the +2M margin)
            if over_stated:
                pct = (pmin / stated_top - 1.0) * 100.0 if stated_top else 0.0
                score += 16
                cap_alternative=True
                reasons.append(f"Starts at {format_money_compact(pmin)} — exceeds the stated budget by {pct:.0f}% (near-budget)")
            elif pmax <= high:
                score += 30
                reasons.append("Full price range fits the budget window")
            else:
                score += 28
                reasons.append(f"Starts at {format_money_compact(pmin)} — inside the budget window")
            if wide and not over_stated:
                reasons.append(f"Wide range ({format_money_compact(pmin)}–{format_money_compact(pmax)}): confirm the exact unit")
        elif pmin < low <= pmax:
            overlap=max(0.0,min(pmax,high)-low)
            overlap_ratio=overlap/max(1.0,pmax-pmin)
            if wide:
                score += 22
                cap_alternative=True
                reasons.append(f"Range {format_money_compact(pmin)}–{format_money_compact(pmax)} reaches the budget: confirm the exact unit")
            else:
                score += 23 if overlap_ratio >= 0.45 else 18
                reasons.append("Price range overlaps the budget window")
        else:
            score += 12
            reasons.append("Below the preferred budget")
        if not wide:
            midpoint=(pmin+pmax)/2
            if abs(midpoint-stated_top)/max(stated_top,1) < 0.10:
                score += 4
                reasons.append("Price is close to the target budget")
    else:
        score += 12

    # Category is handled above (property_category vs listing category).
    raw_unit_pref = clean(client["preferred_unit_type"] or client["unit_type"] or "")
    has_unit_pref = bool(raw_unit_pref)
    desired_unit = canonical_unit_type(raw_unit_pref) if raw_unit_pref else ""
    unit = listing.get("unit_type_canonical") or canonical_unit_type(listing.get("unit_type") or "")
    if has_unit_pref and not desired_unit:
        # Unrecognized client preference cannot satisfy any listing.
        return 0, [], "", False, False
    if desired_unit:
        if unit != desired_unit:
            return 0, [], "", False, False
        score += 20
        reasons.append(f"Unit type: {desired_unit}")
    else:
        score += 10
        if not unit:
            reasons.append("Unit type not classified")

    smin=client["preferred_space_min"] if "preferred_space_min" in client.keys() else None
    smax=client["preferred_space_max"] if "preferred_space_max" in client.keys() else None
    lmin=listing.get("space_min")
    lmax=listing.get("space_max")
    required_missing = False
    if smin is not None or smax is not None:
        target_min=smin if smin is not None else smax
        target_max=smax if smax is not None else smin
        desired_mid=(target_min+target_max)/2
        tolerance_low=target_min*0.80
        tolerance_high=target_max*1.20
        if lmin is not None or lmax is not None:
            lo=lmin if lmin is not None else lmax
            hi=lmax if lmax is not None else lmin
            if lo>hi: lo,hi=hi,lo
            if hi>=tolerance_low and lo<=tolerance_high:
                overlap=max(0,min(hi,tolerance_high)-max(lo,tolerance_low))
                score += 15 if overlap>0 or (lo<=desired_mid<=hi) else 11
                reasons.append("Size is close to the requested area")
            elif lo >= target_min*0.65 and hi <= target_max*1.35:
                score += 7
                reasons.append("Size is a nearby alternative")
            else:
                score += 2
                reasons.append("Size differs from the preferred area")
        else:
            # Client specified an area requirement but the listing lacks size data.
            required_missing = True
            reasons.append("Size not available")
    else:
        score += 8

    if clean(client["bedrooms"] if "bedrooms" in client.keys() else ""):
        wanted=re.sub(r"\D", "", clean(client["bedrooms"]))
        observed=re.sub(r"\D", "", clean(listing.get("unit_type") or ""))
        if wanted and not observed:
            required_missing = True
            reasons.append("Bedrooms not confirmed")
        elif wanted and observed and wanted in observed:
            score += 4
            reasons.append("Bedroom preference appears to fit")

    if client["project"] and normalize_name(client["project"]) == listing.get("normalized_project"):
        score += 5
        reasons.append("Same project already discussed")

    score=min(int(round(score)),100)
    if required_missing:
        band = "alternative" if score >= 50 else "stretch"
    elif cap_alternative:
        band = "alternative"
    elif score >= 80 and (stated_top and pmin is not None and pmin <= stated_top):
        band = "best"
    elif score >= 60 or (budget_fits and score >= 50):
        band = "alternative"
    else:
        band = "stretch"
    return score, reasons, band, True, cap_alternative

@app.route("/api/search")
@login_required()
def global_search():
    q=clean(request.args.get("q"))
    if len(q)<2: return jsonify({"results":[]})
    nq=normalize_text(q); like=f"%{nq}%"
    conn=db(); inventory,live=fetch_live_inventory(conn)
    results=[]
    for item in inventory:
        hay=" ".join([item.get(k) or "" for k in ["project","developer","location","unit_type","normalized_location","normalized_project","normalized_developer"]]).lower()
        if nq in hay:
            results.append({"kind":"Unit","title":item.get("project") or "Project","meta":f'{item.get("normalized_location") or item.get("location") or "Location not specified"} · {item.get("unit_type") or "Listing"} · {item.get("price_display_compact") or "Price on request"}',"url":url_for("listing_detail",listing_id=item["id"])})
            if len(results)>=8: break
    seen=set()
    for item in inventory:
        dev=item.get("normalized_developer") or ""
        if nq in dev.lower() and dev not in seen:
            seen.add(dev); results.append({"kind":"Developer","title":dev,"meta":"Search this developer","url":url_for("projects",developer=dev)})
    if session.get("role")=="admin":
        clients=conn.execute("SELECT id,name,phone FROM clients WHERE lower(name) LIKE ? OR phone LIKE ? ORDER BY id DESC LIMIT 5",(like,like)).fetchall()
    else:
        clients=conn.execute("SELECT id,name,phone FROM clients WHERE assigned_to=? AND (lower(name) LIKE ? OR phone LIKE ?) ORDER BY id DESC LIMIT 5",(session["user_id"],like,like)).fetchall()
    for c in clients:
        results.append({"kind":"Client","title":c["name"],"meta":c["phone"],"url":url_for("client_detail",client_id=c["id"])})
    conn.close(); return jsonify({"results":results[:15]})

@app.route("/clients/<int:client_id>")
@login_required()
def client_detail(client_id):
    conn,c=get_client_or_404(client_id)
    # Work with a mutable copy so multi-location and new fields can be attached.
    c = dict(c)
    c["preferred_locations_list"] = client_locations_for(conn, client_id)
    if not c["preferred_locations_list"] and (c.get("preferred_location") or "").strip():
        c["preferred_locations_list"] = [c["preferred_location"]]
    opps=conn.execute("""SELECT o.*,l.project AS listing_project,l.unit_type,l.location,l.total_price_min,l.total_price_max
        FROM opportunities o LEFT JOIN listings l ON l.id=o.listing_id WHERE o.client_id=? ORDER BY o.id DESC""",(client_id,)).fetchall()
    acts=conn.execute("""SELECT a.*,u.email AS creator_email FROM activities a
        LEFT JOIN users u ON u.id=a.created_by WHERE a.client_id=? ORDER BY a.id DESC LIMIT 50""",(client_id,)).fetchall()
    brokers=conn.execute("SELECT id,email,active FROM users WHERE role='broker' AND (active=1 OR id=?) ORDER BY email",(c["assigned_to"],)).fetchall() if session.get("role")=="admin" else []
    inventory,live=fetch_live_inventory(conn)
    location_options=location_options_for_inventory(inventory)
    selected_location=normalize_location(c["preferred_location"] or "")
    # Preserve a previously entered area even if it is no longer in current inventory.
    if selected_location and selected_location != "No Info" and selected_location not in location_options:
        location_options=sorted(location_options+[selected_location], key=str.casefold)
    selected_unit_type=normalize_unit(c["preferred_unit_type"] or c["unit_type"] or "")
    window=recommendation_window_for(c)
    recs=[]
    if inventory:
        for item in inventory:
            score,reasons,band,eligible,near=recommendation_score(c,item,window)
            if eligible and score>=42:
                item["match_score"]=score
                item["match_reasons"]=reasons
                item["match_band"]=band
                item["match_near_budget"]=bool(near)
                item["match_exact"]=bool(band=="best" and not near)
                # Missing-information reasons for otherwise-included listings.
                if not (item.get("delivery") or "").strip():
                    reasons.append("Delivery not confirmed")
                if not (item.get("finishing") or "").strip():
                    reasons.append("Finishing not specified")
                if not (item.get("payment_plan") or "").strip():
                    reasons.append("Payment plan not provided")
                if item.get("space_min") is None and item.get("space_max") is None:
                    reasons.append("Size to confirm")
                item["match_reasons"]=reasons
                recs.append(item)
    # Exact (within-budget) matches outrank near-budget results.
    recs.sort(key=lambda x:(0 if x.get("match_exact") else 1, -x["match_score"], x.get("project","").lower(), x.get("id",0)))
    # Three groups only: Best Matches, Partial Matches, Near-Budget Alternatives.
    # The legacy "stretch" band is reassigned to Partial (it is the non-near,
    # non-best eligible fallback); no scoring or eligibility rule changes.
    recommendations={"best":[x for x in recs if x["match_band"]=="best"][:8],
                     "alternatives":[x for x in recs if x["match_band"] in ("alternative","stretch") and not x.get("match_near_budget")][:8],
                     "near":[x for x in recs if x["match_band"]=="alternative" and x.get("match_near_budget")][:8]}
    owner_name=c["broker_email"] or "Unassigned"
    creator_name=c["creator_email"] or owner_name
    phone_digits=re.sub(r"\D", "", clean(c["phone"]))
    if phone_digits.startswith("0"):
        phone_digits="20"+phone_digits[1:]
    whatsapp_url=f"https://wa.me/{phone_digits}" if phone_digits else ""
    conn.close()
    return render_template("client_detail.html",client=c,opportunities=opps,activities=acts,
                           recommendations=recommendations,recommendation_window=window,
                           brokers=brokers,owner_name=owner_name,creator_name=creator_name,
                           whatsapp_url=whatsapp_url,location_options=location_options,
                           selected_location=selected_location,selected_unit_type=selected_unit_type,
                           client_locations=c["preferred_locations_list"])

@app.route("/clients/<int:client_id>/activity",methods=["POST"])
@login_required()
def add_activity(client_id):
    conn,c=get_client_or_404(client_id)
    body=clean(request.form.get("body"))
    typ=clean(request.form.get("activity_type")) or "Note"
    allowed={"Note","Call","WhatsApp","Offer","Viewing","Follow-up","Follow-up Completed"}
    if typ not in allowed: typ="Note"
    if body:
        now=utc_now_naive().isoformat()
        conn.execute("INSERT INTO activities(client_id,activity_type,body,created_at,created_by) VALUES(?,?,?,?,?)",(client_id,typ,body,now,session["user_id"]))
        log_audit(conn,"Added client activity","client",client_id,typ)
        conn.commit()
    conn.close()
    return redirect(url_for("client_detail",client_id=client_id))


@app.route("/clients/<int:client_id>/opportunity",methods=["POST"])
@login_required()
def add_opportunity(client_id):
    conn,c=get_client_or_404(client_id)
    listing_id=request.form.get("listing_id",type=int)
    project=clean(request.form.get("project")); offered=clean(request.form.get("offered_price")); notes=clean(request.form.get("notes")); now=utc_now_naive().isoformat()
    if listing_id:
        r=conn.execute("""SELECT l.id FROM listings l LEFT JOIN versions v ON v.id=l.version_id
            WHERE l.id=? AND ((l.source_type='manual' AND EXISTS(
                SELECT 1 FROM manual_projects mp WHERE mp.id=l.manual_project_id AND mp.active=1
            )) OR (l.source_type!='manual' AND v.status='live'))""",(listing_id,)).fetchone()
        if not r:
            conn.close(); abort(404)
    conn.execute("INSERT INTO opportunities(client_id,listing_id,project,offered_price,status,temperature,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",(client_id,listing_id,project,offered,"New",c["temperature"] or "Warm",notes,now,now))
    conn.execute("INSERT INTO activities(client_id,activity_type,body,created_at,created_by) VALUES(?,?,?,?,?)",(client_id,"Offer",f"Added opportunity: {project or 'Property'} · {offered or 'Price not set'}",now,session["user_id"]))
    log_audit(conn,"Added opportunity","client",client_id,project)
    conn.commit(); conn.close()
    return redirect(url_for("client_detail",client_id=client_id))


@app.route("/opportunities/<int:opportunity_id>/status",methods=["POST"])
@login_required()
def update_opportunity_status(opportunity_id):
    conn=db()
    o=conn.execute("SELECT * FROM opportunities WHERE id=?",(opportunity_id,)).fetchone()
    if not o:
        conn.close(); abort(404)
    client_id=o["client_id"]
    extra="" if session.get("role")=="admin" else " AND assigned_to=?"
    args=(client_id,) if session.get("role")=="admin" else (client_id,session["user_id"])
    allowed=conn.execute("SELECT id FROM clients WHERE id=?"+extra,args).fetchone()
    if not allowed:
        conn.close(); abort(404)
    status=clean(request.form.get("status"))
    choices={"New","Interested","Units Sent","Viewing","Negotiation","Won","Lost"}
    if status not in choices: conn.close(); abort(400)
    now=utc_now_naive().isoformat()
    conn.execute("UPDATE opportunities SET status=?,updated_at=? WHERE id=?",(status,now,opportunity_id))
    conn.execute("INSERT INTO activities(client_id,opportunity_id,activity_type,body,created_at,created_by) VALUES(?,?,?,?,?,?)",(client_id,opportunity_id,"Opportunity Updated",f"Opportunity status changed to {status}",now,session["user_id"]))
    log_audit(conn,"Updated opportunity","opportunity",opportunity_id,status)
    conn.commit(); conn.close()
    return redirect(url_for("client_detail",client_id=client_id))


@app.route("/clients")
@login_required()
def clients():
    conn=db()
    base="""SELECT c.*, owner.email AS broker_email, creator.email AS creator_email
        FROM clients c LEFT JOIN users owner ON owner.id=c.assigned_to
        LEFT JOIN users creator ON creator.id=c.created_by"""
    conditions=[]; args=[]
    if session.get("role") != "admin":
        conditions.append("c.assigned_to=?"); args.append(session["user_id"])
    q=clean(request.args.get("q"))
    status=clean(request.args.get("status"))
    temperature=clean(request.args.get("temperature"))
    follow=clean(request.args.get("follow"))
    if q:
        conditions.append("(lower(c.name) LIKE ? OR lower(c.phone) LIKE ? OR lower(COALESCE(c.project,'')) LIKE ?)")
        like=f"%{q.lower()}%"; args += [like,like,like]
    if status: conditions.append("c.status=?"); args.append(status)
    if temperature: conditions.append("c.temperature=?"); args.append(temperature)
    today = cairo_now().strftime("%Y-%m-%d")
    if follow == "today":
        s, e = cairo_day_utc_bounds(today)
        conditions.append("c.followup_at >= ? AND c.followup_at < ?")
        args += [s, e]
    where=(" WHERE " + " AND ".join(conditions)) if conditions else ""
    rows=conn.execute(base+where+" ORDER BY CASE WHEN c.followup_at IS NULL THEN 1 ELSE 0 END, datetime(c.followup_at) ASC,c.id DESC",args).fetchall()
    scope="" if session.get("role")=="admin" else " AND c.assigned_to=?"
    scope_args=() if session.get("role")=="admin" else (session["user_id"],)
    due=conn.execute(base+" WHERE c.followup_at IS NOT NULL AND datetime(c.followup_at)<=datetime('now') AND c.status NOT IN ('Closed','Not Interested')"+scope+" ORDER BY datetime(c.followup_at) ASC",scope_args).fetchall()
    s_today, e_today = cairo_day_utc_bounds(today)
    upcoming=conn.execute(base+" WHERE c.followup_at IS NOT NULL AND c.followup_at >= ? AND c.followup_at < ? AND datetime(c.followup_at)>datetime('now') AND c.status NOT IN ('Closed','Not Interested')"+scope+" ORDER BY datetime(c.followup_at) ASC",(s_today, e_today)+scope_args).fetchall()
    brokers=conn.execute("SELECT id,email FROM users WHERE role='broker' AND active=1 ORDER BY email").fetchall() if session.get("role")=="admin" else []
    inventory,_=fetch_live_inventory(conn); location_options=location_options_for_inventory(inventory)
    # Attach preferred locations list for display.
    def _attach(rows):
        out=[]
        for r in rows:
            d=dict(r)
            d["preferred_locations_list"]=client_locations_for(conn, r["id"])
            if not d["preferred_locations_list"] and (d.get("preferred_location") or "").strip():
                d["preferred_locations_list"]=[d["preferred_location"]]
            out.append(d)
        return out
    rows=_attach(rows); due=_attach(due); upcoming=_attach(upcoming)
    conn.close()
    return render_template("clients.html",clients=rows,due_clients=due,upcoming_clients=upcoming,
                           prefill_project=request.args.get('project',''),brokers=brokers,location_options=location_options,
                           client_filters={"q":q,"status":status,"temperature":temperature,"follow":follow})


@app.route("/clients/add",methods=["POST"])
@login_required()
def add_client():
    f=request.form; name=clean(f.get("name")); phone=clean(f.get("phone"))
    if not name or not phone:
        flash("Client name and mobile number are required.","error")
        return redirect(url_for("clients"))
    now=utc_now_naive().isoformat()
    psmin,psmax=parse_space_text(f.get("preferred_space",""))
    followup_raw = clean(f.get("followup_at"))
    followup_utc, followup_err = cairo_local_to_utc_naive(followup_raw)
    if followup_err:
        flash(followup_err, "error")
        return redirect(url_for("clients"))
    conn=db()
    if session.get("role")=="admin":
        assigned=request.form.get("assigned_to",type=int) or session["user_id"]
        valid=conn.execute("SELECT id,role FROM users WHERE id=? AND active=1",(assigned,)).fetchone()
        if not valid or (valid["role"] != "broker" and assigned != session["user_id"]):
            conn.close(); abort(400)
    else:
        assigned=session["user_id"]
    # Multiple preferred locations (searchable multi-select). Stored in junction table; first one mirrors preferred_location.
    locs = [clean(x) for x in (request.form.getlist("preferred_locations") or []) if clean(x)]
    single = clean(f.get("preferred_location"))
    if single and single not in locs:
        locs.append(single)
    text = clean(f.get("preferred_locations_text"))
    if text:
        for part in text.split(","):
            p = clean(part)
            if p and p not in locs:
                locs.append(p)
    primary_loc = locs[0] if locs else clean(f.get("preferred_location"))
    property_category = clean(f.get("property_category"))
    preferred_developer = clean(f.get("preferred_developer"))
    preferred_project = clean(f.get("preferred_project"))
    bathrooms = clean(f.get("bathrooms"))
    priority = clean(f.get("priority")) or "Normal"
    cur=conn.execute("""INSERT INTO clients(
        broker_id,name,phone,project,offered_price,budget,unit_type,notes,followup_at,status,source,temperature,
        preferred_location,preferred_unit_type,preferred_space_min,preferred_space_max,bedrooms,bathrooms,purpose,
        budget_flexibility,next_action,lost_reason,property_category,preferred_developer,preferred_project,priority,
        created_at,updated_at,created_by,assigned_to
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (assigned,name,phone,clean(f.get("project")),clean(f.get("offered_price")),clean(f.get("budget")),clean(f.get("unit_type")),
         clean(f.get("notes")),followup_utc,clean(f.get("status")) or "Pending",clean(f.get("source")),
         clean(f.get("temperature")) or "Warm",primary_loc,clean(f.get("preferred_unit_type")),
         psmin,psmax,clean(f.get("bedrooms")),bathrooms,clean(f.get("purpose")),clean(f.get("budget_flexibility")) or "Flexible",
         clean(f.get("next_action")) or "Follow Up",clean(f.get("lost_reason")),property_category,preferred_developer,preferred_project,priority,
         now,now,session["user_id"],assigned))
    client_id=cur.lastrowid
    for loc in locs:
        try:
            conn.execute("INSERT OR IGNORE INTO client_locations(client_id, location, created_at) VALUES(?,?,?)",
                         (client_id, loc, now))
        except Exception:
            pass
    conn.execute("INSERT INTO activities(client_id,activity_type,body,created_at,created_by) VALUES(?,?,?,?,?)",(client_id,"Lead Created","Lead added to CRM",now,session["user_id"]))
    # The project / offered price typed on the Add Client form becomes a real opportunity on the client's page.
    opp_project=clean(f.get("project")); opp_price=clean(f.get("offered_price"))
    if opp_project or opp_price:
        opp_listing=None
        if opp_project:
            inv,_live=fetch_live_inventory(conn)
            matches=[x for x in inv if x.get("normalized_project")==normalize_name(opp_project)]
            if len(matches)==1:
                opp_listing=matches[0]["id"]
        ocur=conn.execute("INSERT INTO opportunities(client_id,listing_id,project,offered_price,status,temperature,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (client_id,opp_listing,opp_project,opp_price,"New",clean(f.get("temperature")) or "Warm","",now,now))
        conn.execute("INSERT INTO activities(client_id,opportunity_id,activity_type,body,created_at,created_by) VALUES(?,?,?,?,?,?)",
            (client_id,ocur.lastrowid,"Offer",f"Added opportunity: {opp_project or 'Property'} · {opp_price or 'Price not set'}",now,session["user_id"]))
    log_audit(conn,"Created client","client",client_id,f"Assigned to user {assigned}")
    conn.commit(); conn.close()
    return redirect(url_for("client_detail",client_id=client_id))


@app.route("/clients/<int:client_id>/status",methods=["POST"])
@login_required()
def update_client_status(client_id):
    conn,c=get_client_or_404(client_id)
    status=clean(request.form.get("status"))
    allowed={"Pending","Contacted","Interested","Not Interested","Closed","Viewing","Negotiation"}
    if status not in allowed:
        conn.close(); abort(400)
    now=utc_now_naive().isoformat()
    conn.execute("UPDATE clients SET status=?,updated_at=? WHERE id=?",(status,now,client_id))
    log_audit(conn,"Updated client status","client",client_id,status)
    conn.commit(); conn.close()
    return redirect(url_for("clients"))


@app.route("/clients/<int:client_id>/complete-followup",methods=["POST"])
@login_required()
def complete_followup(client_id):
    conn,c=get_client_or_404(client_id)
    now=utc_now_naive().isoformat()
    conn.execute("UPDATE clients SET followup_at=NULL,updated_at=? WHERE id=?",(now,client_id))
    conn.execute("INSERT INTO activities(client_id,activity_type,body,created_at,created_by) VALUES(?,?,?,?,?)",(client_id,"Follow-up Completed",clean(request.form.get("note")) or "Follow-up marked as completed",now,session["user_id"]))
    log_audit(conn,"Completed follow-up","client",client_id)
    conn.commit(); conn.close()
    return redirect(request.referrer or url_for("clients"))


@app.route("/clients/<int:client_id>/edit",methods=["POST"])
@login_required()
def edit_client(client_id):
    conn,c=get_client_or_404(client_id)
    f=request.form
    if not clean(f.get("name")) or not clean(f.get("phone")):
        conn.close()
        flash("Client name and mobile number are required.", "error")
        return redirect(url_for("client_detail", client_id=client_id))
    psmin,psmax=parse_space_text(f.get("preferred_space","")); now=utc_now_naive().isoformat()
    followup_raw = clean(f.get("followup_at"))
    followup_utc, followup_err = cairo_local_to_utc_naive(followup_raw)
    if followup_err:
        conn.close()
        flash(followup_err, "error")
        return redirect(url_for("client_detail", client_id=client_id))
    assigned=c["assigned_to"]
    if session.get("role")=="admin" and f.get("assigned_to"):
        assigned=f.get("assigned_to",type=int)
        valid=conn.execute("SELECT id,role,active FROM users WHERE id=?",(assigned,)).fetchone()
        same_inactive_owner = bool(valid and valid["role"] == "broker" and not valid["active"] and assigned == c["assigned_to"])
        if not valid or (valid["role"] != "broker" and assigned != session["user_id"]) or (not valid["active"] and not same_inactive_owner):
            conn.close(); abort(400)
    locs = [clean(x) for x in (request.form.getlist("preferred_locations") or []) if clean(x)]
    single = clean(f.get("preferred_location"))
    if single and single not in locs:
        locs.append(single)
    text = clean(f.get("preferred_locations_text"))
    if text:
        for part in text.split(","):
            p = clean(part)
            if p and p not in locs:
                locs.append(p)
    primary_loc = locs[0] if locs else clean(f.get("preferred_location"))
    property_category = clean(f.get("property_category"))
    preferred_developer = clean(f.get("preferred_developer"))
    preferred_project = clean(f.get("preferred_project"))
    bathrooms = clean(f.get("bathrooms"))
    priority = clean(f.get("priority")) or "Normal"
    conn.execute("""UPDATE clients SET broker_id=?,assigned_to=?,name=?,phone=?,budget=?,project=?,offered_price=?,unit_type=?,source=?,
        temperature=?,preferred_location=?,preferred_unit_type=?,preferred_space_min=?,preferred_space_max=?,bedrooms=?,bathrooms=?,purpose=?,
        budget_flexibility=?,next_action=?,followup_at=?,notes=?,property_category=?,preferred_developer=?,preferred_project=?,priority=?,
        updated_at=? WHERE id=?""",
        (assigned,assigned,clean(f.get("name")),clean(f.get("phone")),clean(f.get("budget")),clean(f.get("project")),
         clean(f.get("offered_price")),clean(f.get("unit_type")),clean(f.get("source")),clean(f.get("temperature")) or "Warm",
         primary_loc,clean(f.get("preferred_unit_type")),psmin,psmax,clean(f.get("bedrooms")),bathrooms,
         clean(f.get("purpose")),clean(f.get("budget_flexibility")) or "Flexible",clean(f.get("next_action")) or "Follow Up",
         followup_utc,clean(f.get("notes")),property_category,preferred_developer,preferred_project,priority,
         now,client_id))
    # Replace location set
    conn.execute("DELETE FROM client_locations WHERE client_id=?", (client_id,))
    for loc in locs:
        try:
            conn.execute("INSERT OR IGNORE INTO client_locations(client_id, location, created_at) VALUES(?,?,?)",
                         (client_id, loc, now))
        except Exception:
            pass
    conn.execute("INSERT INTO activities(client_id,activity_type,body,created_at,created_by) VALUES(?,?,?,?,?)",(client_id,"Profile Updated","Client profile was updated",now,session["user_id"]))
    if assigned != c["assigned_to"]:
        old_owner=c["broker_email"] or str(c["assigned_to"])
        new_row=conn.execute("SELECT email FROM users WHERE id=?",(assigned,)).fetchone()
        new_owner=new_row["email"] if new_row else str(assigned)
        conn.execute("INSERT INTO activities(client_id,activity_type,body,created_at,created_by) VALUES(?,?,?,?,?)",(client_id,"Ownership Transfer",f"Assigned from {old_owner} to {new_owner}",now,session["user_id"]))
        log_audit(conn,"Transferred client","client",client_id,f"{old_owner} -> {new_owner}")
    else:
        log_audit(conn,"Updated client profile","client",client_id)
    conn.commit(); conn.close()
    return redirect(url_for("client_detail",client_id=client_id))


@app.route("/clients/<int:client_id>/delete",methods=["POST"])
@login_required("admin")
def delete_client(client_id):
    conn,c=get_client_or_404(client_id)
    log_audit(conn,"Deleted client","client",client_id,c["name"])
    conn.execute("DELETE FROM clients WHERE id=?",(client_id,))
    conn.commit(); conn.close()
    return redirect(url_for("clients"))


@app.route("/clients/notifications")
@login_required()
def client_notifications():
    conn=db()
    base="""SELECT id,name,phone,project,followup_at,status FROM clients
        WHERE followup_at IS NOT NULL AND followup_at!='' AND status NOT IN ('Closed','Not Interested')
        AND datetime(followup_at)<=?"""
    now_utc=utc_now_sql()
    if session.get("role")=="admin": rows=conn.execute(base+" ORDER BY datetime(followup_at) ASC LIMIT 20",(now_utc,)).fetchall()
    else: rows=conn.execute(base+" AND assigned_to=? ORDER BY datetime(followup_at) ASC LIMIT 20",(now_utc,session["user_id"])).fetchall()
    conn.close(); return jsonify([dict(r) for r in rows])

def create_manual_unit(conn, project_row, form):
    unit_type=clean(form.get("unit_type"))
    if not unit_type:
        raise ValueError("Unit type is required.")
    price_raw=clean(form.get("total_price"))
    m2_raw=clean(form.get("price_m2"))
    space_raw=clean(form.get("space"))
    pmin,pmax,pwarn=split_numeric_range(price_raw,"price")
    mmin,mmax,mwarn=split_numeric_range(m2_raw,"price_m2")
    smin,smax,swarn=split_numeric_range(space_raw,"space")
    # The manual form intentionally accepts a descriptive price/m² such as "Villa".
    if pwarn and price_raw and price_raw.lower() not in {"call for price","by request","tba","n/a","sold out","no info"}:
        raise ValueError("Enter a numeric total price/range (for example 5M or 4M-6M), or leave it blank.")
    if swarn and space_raw and space_raw.lower() not in {"by request","tba","n/a","no info"}:
        raise ValueError("Enter a valid size or range (for example 150 or 120-160).")
    if m2_raw and mwarn and m2_raw.lower() not in {"villa","townhouse","twin house","chalet","apartment","admin","res","by request","tba","n/a","no info"}:
        raise ValueError("Enter a valid price/m² or leave it blank.")
    original={
        "Source":"Manual", "Unit Type":unit_type, "Total Price":price_raw,
        "Price by meter":m2_raw, "Space":space_raw,
        "Payment Plan":clean(form.get("payment_plan")), "Delivery":clean(form.get("delivery")),
        "Finishing":clean(form.get("finishing")), "Maintenance":clean(form.get("maintenance")),
        "Project Location":project_row["project_location"], "Company Location":project_row["company_location"]
    }
    original.update(parse_additional_fields(form.get("additional_fields", "")))
    cur=conn.execute("""INSERT INTO listings(
        version_id,source_sheet,source_row,original_json,developer,project,location,
        price_m2_min,price_m2_max,total_price_min,total_price_max,space_min,space_max,
        payment_plan,unit_type,delivery,finishing,maintenance,project_location,company_location,
        normalized_developer,normalized_project,normalized_location,normalized_unit_type,
        manual_json,source_type,manual_project_id,created_by,updated_by,listing_uid
    ) VALUES(NULL,'Manual',NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, '{}','manual',?,?,?,?)""",
        (json.dumps(original,ensure_ascii=False),project_row["developer"],project_row["project"],project_row["location"],
         mmin,mmax,pmin,pmax,smin,smax,clean(form.get("payment_plan")),unit_type,clean(form.get("delivery")),
         clean(form.get("finishing")),clean(form.get("maintenance")),project_row["project_location"],project_row["company_location"],
         normalize_name(project_row["developer"]),normalize_name(project_row["project"]),normalize_location(project_row["location"]),
         normalize_unit(unit_type),project_row["id"],session["user_id"],session["user_id"],
         listing_uid({"original":original,"developer":project_row["developer"],"project":project_row["project"],"location":project_row["location"],"unit_type":unit_type,"space_min":smin,"space_max":smax,"project_location":project_row["project_location"],"company_location":project_row["company_location"]}),
         canonical_unit_type(unit_type))
    )  # close execute
    return cur.lastrowid


@app.route("/admin/projects/new",methods=["GET","POST"])
@login_required("admin")
def admin_new_project():
    # Project creation is intentionally AI-first. Manual correction happens in the AI review/edit flow.
    return redirect(url_for("admin_ai_project_import"))

@app.route("/admin/projects/ai-import", methods=["GET", "POST"])
@login_required("admin")
def admin_ai_project_import():
    if request.method == "POST":
        source_text = clean(request.form.get("source_text"))
        if not source_text:
            flash("Paste the project summary first.", "error")
            return render_template("ai_project_import.html", draft=None, source_text="")
        draft = parse_project_summary(source_text)
        return render_template("ai_project_import.html", draft=draft, source_text=source_text)
    return render_template("ai_project_import.html", draft=None, source_text="")


@app.route("/admin/projects/ai-create", methods=["POST"])
@login_required("admin")
def admin_ai_project_create():
    f = request.form
    project, developer, location = clean(f.get("project")), clean(f.get("developer")), clean(f.get("location"))
    if not project or not developer or not location:
        flash("Project name, developer and controlled area are required before creation.", "error")
        return redirect(url_for("admin_ai_project_import"))
    try:
        count = int(f.get("unit_count", "0"))
        if count < 0 or count > 100: raise ValueError
    except ValueError:
        flash("Invalid unit count.", "error")
        return redirect(url_for("admin_ai_project_import"))
    now = utc_now_naive().isoformat()
    conn = db()
    try:
        cur = conn.execute("""INSERT INTO manual_projects(project,developer,location,project_location,company_location,description,created_by,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)""", (project,developer,location,clean(f.get("project_location")),clean(f.get("company_location")),clean(f.get("description")),session["user_id"],now,now))
        project_id = cur.lastrowid
        project_row = conn.execute("SELECT * FROM manual_projects WHERE id=?", (project_id,)).fetchone()
        created_units = 0
        for i in range(count):
            unit_data = {key: clean(f.get(f"units-{i}-{key}")) for key in ["unit_type","space","total_price","price_m2","payment_plan","delivery","finishing","maintenance","additional_fields"]}
            if not unit_data["unit_type"] and not unit_data["space"] and not unit_data["total_price"]:
                continue
            if not unit_data["unit_type"]: unit_data["unit_type"] = "Apartment"
            unit_id = create_manual_unit(conn, project_row, unit_data)
            # Preserve the source line that informed this draft unit.
            source_line = clean(f.get(f"units-{i}-source_line"))
            if source_line:
                row = conn.execute("SELECT original_json FROM listings WHERE id=?", (unit_id,)).fetchone()
                original = json.loads(row["original_json"] or "{}")
                original["AI Import Source"] = source_line
                conn.execute("UPDATE listings SET original_json=? WHERE id=?", (json.dumps(original, ensure_ascii=False), unit_id))
            created_units += 1
        log_audit(conn, "Created project with AI import review", "project", project_id,
                  f"{project} / {developer} / {location}; {created_units} units; source pasted and admin-confirmed")
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        flash(f"Project was not created: {exc}", "error")
        return redirect(url_for("admin_ai_project_import"))
    conn.close()
    flash(f"Project created after review with {created_units} unit(s).", "success")
    return redirect(url_for("admin_manual_project", project_id=project_id))


@app.route("/admin/projects/<int:project_id>")
@login_required("admin")
def admin_manual_project(project_id):
    conn=db()
    project=conn.execute("SELECT * FROM manual_projects WHERE id=?",(project_id,)).fetchone()
    if not project:
        conn.close(); abort(404)
    units=conn.execute("SELECT * FROM listings WHERE source_type='manual' AND manual_project_id=? ORDER BY id DESC",(project_id,)).fetchall()
    units=[row_to_listing(x) for x in units]
    conn.close()
    return render_template("manual_project_detail.html",project=project,units=units)


@app.route("/admin/projects/<int:project_id>/edit",methods=["POST"])
@login_required("admin")
def admin_edit_manual_project(project_id):
    conn=db(); p=conn.execute("SELECT * FROM manual_projects WHERE id=?",(project_id,)).fetchone()
    if not p:
        conn.close(); abort(404)
    f=request.form; project=clean(f.get("project")); developer=clean(f.get("developer")); location=clean(f.get("location"))
    if not project or not developer or not location:
        conn.close(); flash("Project name, developer and location are required.","error")
        return redirect(url_for("admin_manual_project",project_id=project_id))
    conn.execute("""UPDATE manual_projects SET project=?,developer=?,location=?,project_location=?,company_location=?,description=?,updated_at=? WHERE id=?""",
        (project,developer,location,clean(f.get("project_location")),clean(f.get("company_location")),clean(f.get("description")),utc_now_naive().isoformat(),project_id))
    # Keep project-level values synchronized to its units; unit-level overrides remain explicit.
    project_location=clean(f.get("project_location")); company_location=clean(f.get("company_location"))
    unit_rows=conn.execute("SELECT id,manual_json FROM listings WHERE source_type='manual' AND manual_project_id=?",(project_id,)).fetchall()
    for unit_row in unit_rows:
        unit_manual=json.loads(unit_row["manual_json"] or "{}")
        # These attributes belong to the project, so the parent project edit is authoritative.
        for field in ("project","developer","location","project_location","company_location"):
            unit_manual.pop(field,None)
        conn.execute("""UPDATE listings SET project=?,developer=?,location=?,project_location=?,company_location=?,
            normalized_project=?,normalized_developer=?,normalized_location=?,manual_json=?,updated_by=? WHERE id=?""",
            (project,developer,location,project_location,company_location,normalize_name(project),normalize_name(developer),
             normalize_location(location),json.dumps(unit_manual,ensure_ascii=False),session["user_id"],unit_row["id"]))
    log_audit(conn,"Updated manual project","project",project_id,f"{project} / {developer} / {location}")
    conn.commit(); conn.close(); flash("Project details updated.","success")
    return redirect(url_for("admin_manual_project",project_id=project_id))


@app.route("/admin/projects/<int:project_id>/units/add",methods=["POST"])
@login_required("admin")
def admin_add_manual_unit(project_id):
    conn=db(); project=conn.execute("SELECT * FROM manual_projects WHERE id=? AND active=1",(project_id,)).fetchone()
    if not project:
        conn.close(); abort(404)
    try:
        unit_id=create_manual_unit(conn,project,request.form)
    except ValueError as exc:
        conn.close(); flash(str(exc),"error")
        return redirect(url_for("admin_manual_project",project_id=project_id))
    log_audit(conn,"Added manual unit","listing",unit_id,f"Project: {project['project']}")
    conn.commit(); conn.close(); flash("Unit added to the project inventory.","success")
    return redirect(url_for("admin_manual_project",project_id=project_id))


@app.route("/admin/listings/<int:listing_id>/delete",methods=["POST"])
@login_required("admin")
def admin_delete_manual_unit(listing_id):
    conn=db()
    unit=conn.execute("SELECT * FROM listings WHERE id=? AND source_type='manual'",(listing_id,)).fetchone()
    if not unit:
        conn.close(); abort(404)
    linked=conn.execute("SELECT COUNT(*) FROM opportunities WHERE listing_id=?",(listing_id,)).fetchone()[0]
    if linked:
        conn.close(); flash("This unit is linked to a client opportunity. Update the opportunity first; the unit was not deleted.","error")
        return redirect(url_for("admin_manual_project",project_id=unit["manual_project_id"]))
    log_audit(conn,"Deleted manual unit","listing",listing_id,unit["project"])
    conn.execute("DELETE FROM favorites WHERE listing_id=?",(listing_id,))
    conn.execute("DELETE FROM listings WHERE id=?",(listing_id,))
    conn.commit(); conn.close()
    flash("Manual unit deleted.","success")
    return redirect(url_for("admin_manual_project",project_id=unit["manual_project_id"]))


@app.route("/admin/projects/<int:project_id>/archive",methods=["POST"])
@login_required("admin")
def admin_archive_manual_project(project_id):
    conn=db(); p=conn.execute("SELECT * FROM manual_projects WHERE id=?",(project_id,)).fetchone()
    if not p:
        conn.close(); abort(404)
    next_state=0 if p["active"] else 1
    conn.execute("UPDATE manual_projects SET active=?,updated_at=? WHERE id=?",(next_state,utc_now_naive().isoformat(),project_id))
    if next_state:
        conn.execute("UPDATE listings SET source_type='manual' WHERE manual_project_id=?",(project_id,))
        log_audit(conn,"Restored manual project","project",project_id,p["project"])
        flash("Project restored to live inventory.","success")
    else:
        log_audit(conn,"Archived manual project","project",project_id,p["project"])
        flash("Project archived. Brokers will no longer see its units.","success")
    conn.commit(); conn.close()
    return redirect(url_for("admin"))


@app.route("/admin/audit")
@login_required("admin")
def admin_audit():
    conn=db()
    rows=conn.execute("""SELECT a.*,u.email AS actor_email FROM audit_logs a
        LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 300""").fetchall()
    conn.close()
    return render_template("audit.html",rows=rows)

@app.route("/admin")
@login_required("admin")
def admin():
    conn=db()
    versions=conn.execute("SELECT v.*,u.email AS creator FROM versions v LEFT JOIN users u ON u.id=v.created_by ORDER BY v.id DESC").fetchall()
    users=conn.execute("SELECT id,email,role,active,created_at FROM users ORDER BY role,email").fetchall()
    inventory,live_version_row=fetch_live_inventory(conn)
    live_listings=inventory[:300]
    manual_projects=conn.execute("""SELECT p.*,u.email AS creator_email,COUNT(l.id) AS unit_count
        FROM manual_projects p LEFT JOIN users u ON u.id=p.created_by
        LEFT JOIN listings l ON l.manual_project_id=p.id AND l.source_type='manual'
        GROUP BY p.id ORDER BY p.active DESC,p.id DESC""").fetchall()
    client_count=conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    audit_count=conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    conn.close()
    return render_template("admin.html",versions=versions,users=users,live_listings=live_listings,
                           manual_projects=manual_projects,client_count=client_count,audit_count=audit_count)

@app.route("/admin/upload", methods=["POST"])
@login_required("admin")
def upload():
    request_id = uuid.uuid4().hex[:10]
    version_id = None
    path = None
    upload_log(f"{request_id} request received")
    try:
        f = request.files.get("file")
        if not f or not f.filename or not f.filename.lower().endswith((".xlsx", ".xlsm")):
            upload_log(f"{request_id} rejected: missing/unsupported file")
            flash("Please upload an .xlsx or .xlsm workbook.", "error")
            return redirect(url_for("admin"))

        safe_name = Path(f.filename).name
        stored = f"{uuid.uuid4().hex}_{safe_name}"
        path = UPLOADS / stored
        upload_log(f"{request_id} saving file: {safe_name}")
        f.save(path)
        upload_log(f"{request_id} file saved: {path.stat().st_size} bytes")

        conn = db()
        try:
            cur = conn.execute(
                "INSERT INTO versions(filename,status,created_at,created_by) VALUES(?,?,?,?)",
                (safe_name, "draft", utc_now_naive().isoformat(), session["user_id"])
            )
            version_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()
        upload_log(f"{request_id} draft record created: version_id={version_id}")

        upload_log(f"{request_id} parser started")
        summary = import_workbook(path, version_id)
        upload_log(f"{request_id} parser finished: imported={summary['imported_rows']} warnings={summary['warnings']} serious={summary['serious_errors']}")

        audit_conn = db()
        try:
            log_audit(audit_conn, "Imported Excel draft", "version", version_id,
                      f"{safe_name} · {summary['imported_rows']} rows · {summary['serious_errors']} serious errors")
            audit_conn.commit()
        finally:
            audit_conn.close()
        upload_log(f"{request_id} audit saved; redirecting to version {version_id}")

        if summary["serious_errors"]:
            flash(f"Draft imported with {summary['serious_errors']} serious error(s). Fix the source workbook and upload again.", "error")
        else:
            flash(f"Draft imported: {summary['imported_rows']} rows, {summary['warnings']} warning(s).", "success")
        return redirect(url_for("version_detail", version_id=version_id))

    except Exception as exc:
        detail = traceback.format_exc()
        upload_log(f"{request_id} FAILED: {type(exc).__name__}: {exc}")
        upload_log(detail)
        # Keep the failed attempt visible in Import History, with its diagnostic.
        if version_id is not None:
            try:
                conn = db()
                try:
                    summary = {
                        "total_rows": 0, "imported_rows": 0, "rejected_rows": 0,
                        "warnings": 0, "info": 0, "serious_errors": 1,
                        "warning_messages": [], "info_messages": [],
                        "serious_messages": [f"Import failed ({request_id}): {type(exc).__name__}: {exc}"]
                    }
                    conn.execute("UPDATE versions SET serious_errors=1,summary_json=? WHERE id=?",
                                 (json.dumps(summary, ensure_ascii=False), version_id))
                    conn.commit()
                finally:
                    conn.close()
            except Exception as db_exc:
                upload_log(f"{request_id} could not mark failed draft: {db_exc}")
        flash(f"Excel import failed ({request_id}). Check data/upload_debug.log and send it for diagnosis.", "error")
        return redirect(url_for("admin"))


@app.errorhandler(413)
def upload_too_large(_error):
    flash("The workbook is larger than the 32 MB upload limit.", "error")
    return redirect(url_for("admin"))


@app.route("/admin/upload-debug-log")
@login_required("admin")
def admin_upload_debug_log():
    from flask import send_file
    log_path = DATA / "upload_debug.log"
    if not log_path.exists():
        flash("No upload diagnostics have been recorded yet.", "info")
        return redirect(url_for("admin"))
    return send_file(log_path, as_attachment=True, download_name="upload_debug.log")

@app.route("/admin/version/<int:version_id>")
@login_required("admin")
def version_detail(version_id):
    conn=db()
    v=conn.execute("SELECT * FROM versions WHERE id=?",(version_id,)).fetchone()
    conn.close()
    if not v: abort(404)
    summary=json.loads(v["summary_json"] or "{}")
    return render_template("version.html", version=v, summary=summary)

@app.route("/admin/version/<int:version_id>/publish", methods=["POST"])
@login_required("admin")
def publish(version_id):
    conn=db()
    v=conn.execute("SELECT * FROM versions WHERE id=?",(version_id,)).fetchone()
    if not v: abort(404)
    if v["status"]!="draft":
        flash("Only a draft can be published.", "error"); conn.close()
        return redirect(url_for("version_detail",version_id=version_id))
    if v["serious_errors"]>0:
        flash("This draft has serious errors and cannot be published.", "error"); conn.close()
        return redirect(url_for("version_detail",version_id=version_id))

    # Capture the old live version's listing uid -> id map before flipping.
    old_live = conn.execute("SELECT id, listing_uid FROM listings WHERE version_id=(SELECT id FROM versions WHERE status='live' ORDER BY id DESC LIMIT 1)").fetchall()
    old_map = {}
    for r in old_live:
        if r["listing_uid"]:
            old_map.setdefault(r["listing_uid"], []).append(r["id"])

    new_listings = conn.execute("SELECT id, listing_uid FROM listings WHERE version_id=?", (version_id,)).fetchall()
    new_map = {}
    for r in new_listings:
        if r["listing_uid"]:
            new_map[r["listing_uid"]] = r["id"]  # first wins

    try:
        conn.execute("UPDATE versions SET status='archived' WHERE status='live'")
        conn.execute("UPDATE versions SET status='live' WHERE id=?",(version_id,))

        # Re-point favorites/opportunities from old live listings to new live
        # listings by listing_uid. Only when a matching new listing exists;
        # otherwise keep the old reference (never delete). Importing a draft
        # does not touch references; only publishing does.
        for uid, old_ids in old_map.items():
            new_id = new_map.get(uid)
            if new_id is None:
                continue
            for old_id in old_ids:
                conn.execute("UPDATE favorites SET listing_id=? WHERE listing_id=?", (new_id, old_id))
                conn.execute("UPDATE opportunities SET listing_id=? WHERE listing_id=?", (new_id, old_id))

        log_audit(conn,"Published inventory version","version",version_id,v["filename"])
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        flash(f"Publish failed: {exc}", "error")
        return redirect(url_for("version_detail",version_id=version_id))
    conn.close()
    flash("Draft published successfully.", "success")
    return redirect(url_for("dashboard"))

@app.route("/admin/version/<int:version_id>/restore", methods=["POST"])
@login_required("admin")
def restore(version_id):
    conn=db()
    v=conn.execute("SELECT * FROM versions WHERE id=?",(version_id,)).fetchone()
    if not v:
        conn.close(); abort(404)

    status = (v["status"] or "").strip().lower()
    if status == "live":
        # Safe no-op: already live. No audit entry, no record changes.
        conn.close()
        flash("This version is already live.", "success")
        return redirect(url_for("dashboard"))
    if status != "archived":
        conn.close()
        flash("Only an archived version can be restored.", "error")
        return redirect(url_for("version_detail", version_id=version_id))

    # Resolve serious_errors from the column first, then the JSON summary as a
    # fallback. Fail safe if neither is readable/valid.
    serious = None
    try:
        serious = int(v["serious_errors"])
    except (TypeError, ValueError):
        serious = None
    if serious is None:
        try:
            summary = json.loads(v["summary_json"] or "{}")
            serious = int(summary.get("serious_errors", 0))
        except (TypeError, ValueError, json.JSONDecodeError):
            serious = None
    if serious is None:
        conn.close()
        flash("This version's validation metadata is unreadable; restore is blocked for safety.", "error")
        return redirect(url_for("version_detail", version_id=version_id))
    if serious > 0:
        conn.close()
        flash("This version has serious errors and cannot be restored.", "error")
        return redirect(url_for("version_detail", version_id=version_id))

    # Count listings in the target version (for the empty-version notice).
    listing_count = conn.execute("SELECT COUNT(*) FROM listings WHERE version_id=?", (version_id,)).fetchone()[0]

    try:
        conn.execute("UPDATE versions SET status='archived' WHERE status='live'")
        conn.execute("UPDATE versions SET status='live' WHERE id=?",(version_id,))
        # No listing rows, references, or listing_uids are modified by restore.
        log_audit(conn,"Restored inventory version","version",version_id,v["filename"])
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        flash(f"Restore failed: {exc}", "error")
        return redirect(url_for("version_detail", version_id=version_id))
    conn.close()
    if listing_count == 0:
        flash("Archived version restored as live. Live inventory now contains manual listings only.", "warning")
    else:
        flash("Archived version restored as live.", "success")
    return redirect(url_for("dashboard"))

@app.route("/admin/users", methods=["POST"])
@login_required("admin")
def users():
    action=request.form.get("action")
    conn=db()
    if action=="create":
        email=clean(request.form.get("email")).lower()
        password=request.form.get("password","")
        role="broker"
        if not email or not password:
            flash("Email and password are required.", "error")
        elif len(password) < 10:
            flash("Broker passwords must contain at least 10 characters.", "error")
        else:
            try:
                cur=conn.execute("INSERT INTO users(email,password_hash,role,created_at,must_change_password) VALUES(?,?,?,?,1)",
                             (email,generate_password_hash(password),role,utc_now_naive().isoformat()))
                log_audit(conn,"Created broker account","user",cur.lastrowid,email)
                conn.commit(); flash("Broker account created.", "success")
            except sqlite3.IntegrityError:
                flash("That email already exists.", "error")
    elif action=="toggle":
        raw_uid = request.form.get("user_id", type=int)
        if raw_uid is None or raw_uid <= 0:
            flash("Invalid broker account selected.", "error")
        else:
            uid = raw_uid
            if uid != session["user_id"]:
                conn.execute("UPDATE users SET active=1-active WHERE id=? AND role='broker'",(uid,))
                log_audit(conn,"Changed broker account status","user",uid)
                conn.commit()
                flash("User status updated.", "success")
    elif action=="password":
        uid = request.form.get("user_id", type=int)
        if uid is None or uid <= 0:
            flash("Invalid broker account selected.", "error")
            conn.close()
            return redirect(url_for("dashboard"))
        pw=request.form.get("password","")
        if len(pw) < 10:
            flash("Broker passwords must contain at least 10 characters.", "error")
        else:
            updated=conn.execute("UPDATE users SET password_hash=?, must_change_password=1 WHERE id=? AND role='broker'",(generate_password_hash(pw),uid))
            if updated.rowcount:
                log_audit(conn,"Reset broker password","user",uid)
                conn.commit(); flash("Password updated.", "success")
            else:
                flash("Broker account not found.", "error")
    conn.close()
    return redirect(url_for("dashboard"))

@app.template_filter("money")
def money_filter(v):
    return format_money(v)

@app.template_filter("budget")
def budget_filter(v):
    if v is None or str(v).strip() == "":
        return ""
    a, b = parse_budget_text(v)
    if a is not None:
        return format_money(a)
    n = parse_number_token(v)
    if n is not None:
        return format_money(n)
    return str(v)

@app.template_filter("money_compact")
def money_compact_filter(v):
    return format_money_compact(v)

@app.context_processor
def inject():
    conn=db()
    try:
        if session.get('user_id'):
            q="SELECT COUNT(*) AS n FROM clients WHERE followup_at IS NOT NULL AND status NOT IN ('Closed','Not Interested') AND datetime(followup_at)<=?"
            now_utc=utc_now_sql()
            args=(now_utc,) if session.get('role')=='admin' else (now_utc, session.get('user_id'))
            if session.get('role')!='admin': q += " AND assigned_to=?"
            notification_count=conn.execute(q,args).fetchone()['n']
        else:
            notification_count=0
    finally:
        conn.close()
    return {"current_role":session.get("role"), "current_email":session.get("email"), "notification_count":notification_count}

if __name__ == "__main__":
    # Simple log rotation for office deployments.
    for _log_name in ("portal.log", "upload_debug.log"):
        _lp = DATA / "logs" / _log_name
        try:
            if _lp.exists() and _lp.stat().st_size > 5 * 1024 * 1024:
                _lp.replace(_lp.with_suffix(_lp.suffix + ".1"))
        except Exception:
            pass
    init_db()
    refresh_listing_location_matches()
    host = os.environ.get("BROKER_PORTAL_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("BROKER_PORTAL_DEBUG", "0") == "1"
    if debug:
        app.run(host=host, port=port, debug=True)
    else:
        try:
            from waitress import serve
            serve(app, host=host, port=port, threads=8)
        except ImportError:
            print("Waitress is not installed; falling back to Flask's local server. Install requirements.txt for team use.")
            app.run(host=host, port=port, debug=False)
