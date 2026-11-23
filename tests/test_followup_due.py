"""Follow-up due/upcoming consistency tests (UTC)."""
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from werkzeug.security import generate_password_hash

CSRF = "test-csrf-token"


def _mk_user(portal, role="broker", active=1):
    conn = portal.db()
    try:
        email = f"{role}.{uuid.uuid4().hex[:8]}@test"
        cur = conn.execute(
            "INSERT INTO users(email,password_hash,role,active,created_at,must_change_password) VALUES(?,?,?,?,?,0)",
            (email, generate_password_hash("Broker123456"), role, active, "2026-01-01T00:00:00"),
        )
        uid = cur.lastrowid
        conn.commit()
        return uid, email
    finally:
        conn.close()


def _mk_client(portal, owner_uid, name, followup_utc_naive):
    conn = portal.db()
    try:
        cur = conn.execute(
            "INSERT INTO clients(broker_id,assigned_to,name,phone,status,created_at,updated_at,created_by,followup_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (owner_uid, owner_uid, name, "0100" + uuid.uuid4().hex[:7], "Pending",
             "2026-01-01T00:00:00", "2026-01-01T00:00:00", owner_uid,
             followup_utc_naive.isoformat() if hasattr(followup_utc_naive, "isoformat") else followup_utc_naive),
        )
        cid = cur.lastrowid
        conn.commit()
        return cid
    finally:
        conn.close()


@pytest.mark.parametrize("tzname", ["UTC", "Africa/Cairo", "America/New_York"])
def test_followup_due_consistency(portal, app_client, tzname):
    os.environ["TZ"] = tzname
    try:
        time.tzset()
    except AttributeError:
        pass

    uid, email = _mk_user(portal)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    names = {
        "late30": f"Late30-{uuid.uuid4().hex[:6]}",
        "plus90": f"Plus90-{uuid.uuid4().hex[:6]}",
        "plus2d": f"Plus2d-{uuid.uuid4().hex[:6]}",
        "minus2d": f"Minus2d-{uuid.uuid4().hex[:6]}",
    }
    _mk_client(portal, uid, names["late30"], now - timedelta(minutes=30, microseconds=123456))  # microseconds case
    _mk_client(portal, uid, names["plus90"], now + timedelta(minutes=90))
    _mk_client(portal, uid, names["plus2d"], now + timedelta(days=2))
    _mk_client(portal, uid, names["minus2d"], now - timedelta(days=2))

    with app_client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "broker"
        sess["email"] = email
        sess["_csrf"] = CSRF

    # notifications endpoint
    resp = app_client.get("/clients/notifications")
    assert resp.status_code == 200
    notif = resp.get_json()
    notif_names = {n["name"] for n in notif}
    assert names["late30"] in notif_names
    assert names["minus2d"] in notif_names
    assert names["plus90"] not in notif_names
    assert names["plus2d"] not in notif_names
    assert len(notif) == 2

    # dashboard
    resp = app_client.get("/dashboard")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert names["late30"] in html
    assert names["minus2d"] in html
    assert names["plus90"] in html  # upcoming

    # clients page
    resp = app_client.get("/clients")
    assert resp.status_code == 200
    html2 = resp.get_data(as_text=True)
    assert names["late30"] in html2
    assert names["minus2d"] in html2
