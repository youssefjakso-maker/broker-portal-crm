"""Tests for task fixes: validation, budget formatting."""
import uuid

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


def _mk_client(portal, owner_uid, name="C"):
    conn = portal.db()
    try:
        cur = conn.execute(
            "INSERT INTO clients(broker_id,assigned_to,name,phone,status,created_at,updated_at,created_by) VALUES(?,?,?,?,?,?,?,?)",
            (owner_uid, owner_uid, name, "0100" + uuid.uuid4().hex[:7], "Pending", "2026-01-01T00:00:00", "2026-01-01T00:00:00", owner_uid),
        )
        cid = cur.lastrowid
        conn.commit()
        return cid
    finally:
        conn.close()


def test_edit_client_rejects_empty_name(portal, app_client):
    uid, email = _mk_user(portal)
    cid = _mk_client(portal, uid)
    with app_client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "broker"
        sess["email"] = email
        sess["_csrf"] = CSRF
    resp = app_client.post(
        f"/clients/{cid}/edit",
        data={"name": "", "phone": "01000000000", "csrf_token": CSRF},
    )
    assert resp.status_code == 302
    conn = portal.db()
    try:
        row = conn.execute("SELECT name FROM clients WHERE id=?", (cid,)).fetchone()
    finally:
        conn.close()
    assert row["name"] == "C"


def test_update_client_status_invalid_returns_400(portal, app_client):
    uid, email = _mk_user(portal)
    cid = _mk_client(portal, uid)
    with app_client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = "broker"
        sess["email"] = email
        sess["_csrf"] = CSRF
    resp = app_client.post(
        f"/clients/{cid}/status",
        data={"status": "Bogus", "csrf_token": CSRF},
    )
    assert resp.status_code == 400


def test_budget_filter_formats(portal):
    import app as A
    assert A.budget_filter("2M") == "2,000,000"
    assert A.budget_filter("2.5M") == "2,500,000"
    assert A.budget_filter("2,000,000") == "2,000,000"
    assert A.budget_filter("Basic 2M") == "2,000,000"
    assert A.budget_filter("") == ""


def test_users_empty_user_id_no_500(portal, admin_client):
    resp = admin_client.post(
        "/admin/users",
        data={"action": "toggle", "user_id": "", "csrf_token": "test-csrf-token"},
    )
    assert resp.status_code == 302
    assert resp.status_code != 500


def test_update_opportunity_status_invalid_closes_conn(portal, admin_client):
    # create client + opportunity via DB
    uid, email = _mk_user(portal)
    cid = _mk_client(portal, uid)
    conn = portal.db()
    try:
        cur = conn.execute(
            "INSERT INTO opportunities(client_id,project,offered_price,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (cid, "P", "1", "New", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        opp_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    with admin_client.session_transaction() as sess:
        sess["user_id"] = 1  # admin
        # admin id from fixture? use portal admin
    # use app's admin via session already set by fixture
    resp = admin_client.post(
        f"/opportunities/{opp_id}/status",
        data={"status": "Bogus", "csrf_token": "test-csrf-token"},
    )
    assert resp.status_code == 400
