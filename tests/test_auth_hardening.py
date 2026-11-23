"""P1.7.2 - server-side authentication / RBAC hardening tests.

All checks are server-side. Sessions are created directly in the test client
(never by trusting form/query values). Every test uses the temporary database
created by conftest; the persistent project database is never opened.
"""
import uuid

import pytest
from werkzeug.security import generate_password_hash

CSRF = "test-csrf-token"


def _mk_user(portal, role="broker", active=1, password="Broker123456", email=None):
    conn = portal.db()
    try:
        email = email or f"{role}.{uuid.uuid4().hex[:8]}@test"
        cur = conn.execute(
            "INSERT INTO users(email,password_hash,role,active,created_at,must_change_password) "
            "VALUES(?,?,?,?,?,0)",
            (email, generate_password_hash(password), role, active, "2026-01-01T00:00:00"),
        )
        uid = cur.lastrowid
        conn.commit()
        return uid, email, password
    finally:
        conn.close()


def _mk_client(portal, owner_uid, name, followup_at=None):
    conn = portal.db()
    try:
        cur = conn.execute(
            """INSERT INTO clients(broker_id,assigned_to,name,phone,status,created_at,updated_at,created_by,followup_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                owner_uid,
                owner_uid,
                name,
                "0100" + uuid.uuid4().hex[:7],
                "Pending",
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:00",
                owner_uid,
                followup_at,
            ),
        )
        cid = cur.lastrowid
        conn.commit()
        return cid
    finally:
        conn.close()


def _session(client, uid, role, email):
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["role"] = role
        sess["email"] = email
        sess["_csrf"] = CSRF


def _client_row(portal, client_id):
    conn = portal.db()
    try:
        return dict(conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone())
    finally:
        conn.close()


def _count(portal, sql, args=()):
    conn = portal.db()
    try:
        return conn.execute(sql, args).fetchone()[0]
    finally:
        conn.close()


@pytest.fixture()
def rbac(portal, admin_user_id):
    broker_a, email_a, _ = _mk_user(portal)
    broker_b, email_b, _ = _mk_user(portal)
    client_a = _mk_client(portal, broker_a, "Broker A Client")
    client_b = _mk_client(portal, broker_b, "Broker B Client", followup_at="2026-12-01T10:00:00")
    return {
        "portal": portal,
        "admin": admin_user_id,
        "a": broker_a,
        "a_email": email_a,
        "b": broker_b,
        "b_email": email_b,
        "client_a": client_a,
        "client_b": client_b,
    }


# ---------------------------------------------------------------- authentication

def test_unauthenticated_protected_route_redirects_to_login(app_client):
    response = app_client.get("/dashboard")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_login_success_and_session_rotation(portal, app_client):
    uid, email, password = _mk_user(portal, email="login.ok@test")
    with app_client.session_transaction() as sess:
        sess["_csrf"] = CSRF
        sess["stale_marker"] = "must-be-removed"

    response = app_client.post(
        "/login", data={"email": email, "password": password, "csrf_token": CSRF}
    )
    assert response.status_code == 302
    with app_client.session_transaction() as sess:
        assert sess["user_id"] == uid
        assert "stale_marker" not in sess


def test_login_rejects_invalid_password(portal, app_client):
    uid, email, password = _mk_user(portal, email="login.bad@test")
    with app_client.session_transaction() as sess:
        sess["_csrf"] = CSRF
    response = app_client.post(
        "/login", data={"email": email, "password": "wrong-password", "csrf_token": CSRF}
    )
    assert response.status_code == 200
    with app_client.session_transaction() as sess:
        assert "user_id" not in sess


def test_inactive_user_cannot_log_in(portal, app_client):
    uid, email, password = _mk_user(portal, active=0, email="login.inactive@test")
    with app_client.session_transaction() as sess:
        sess["_csrf"] = CSRF
    response = app_client.post(
        "/login", data={"email": email, "password": password, "csrf_token": CSRF}
    )
    assert response.status_code == 200
    with app_client.session_transaction() as sess:
        assert "user_id" not in sess


def test_logout_clears_session(app_client, rbac):
    _session(app_client, rbac["a"], "broker", rbac["a_email"])
    response = app_client.get("/logout")
    assert response.status_code == 302
    with app_client.session_transaction() as sess:
        assert "user_id" not in sess


def test_inactive_user_cannot_access_protected_route(portal, app_client):
    uid, email, _ = _mk_user(portal, active=0, email="inactive.session@test")
    _session(app_client, uid, "broker", email)
    response = app_client.get("/dashboard")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    with app_client.session_transaction() as sess:
        assert "user_id" not in sess


def test_existing_session_rejected_after_user_becomes_inactive(portal, app_client):
    uid, email, _ = _mk_user(portal, email="deactivated.mid@test")
    _session(app_client, uid, "broker", email)
    assert app_client.get("/dashboard").status_code == 200

    conn = portal.db()
    try:
        conn.execute("UPDATE users SET active=0 WHERE id=?", (uid,))
        conn.commit()
    finally:
        conn.close()

    response = app_client.get("/dashboard")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    with app_client.session_transaction() as sess:
        assert "user_id" not in sess


def test_session_role_manipulation_cannot_elevate_broker(portal, rbac, app_client):
    _session(app_client, rbac["a"], "admin", rbac["a_email"])

    response = app_client.get("/admin")
    assert response.status_code == 403
    with app_client.session_transaction() as sess:
        assert sess["role"] == "broker"

    email = f"escalation.{uuid.uuid4().hex[:8]}@test"
    response = app_client.post(
        "/admin/users",
        data={"action": "create", "email": email, "password": "Abcdef12345", "csrf_token": CSRF},
    )
    assert response.status_code == 403
    assert _count(portal, "SELECT COUNT(*) FROM users WHERE email=?", (email,)) == 0


# ---------------------------------------------------------------- ownership

def test_broker_can_access_own_client(rbac, app_client):
    _session(app_client, rbac["a"], "broker", rbac["a_email"])
    response = app_client.get(f"/clients/{rbac['client_a']}")
    assert response.status_code == 200
    assert b"Broker A Client" in response.data


def test_broker_cannot_access_other_client_by_url(rbac, app_client):
    _session(app_client, rbac["a"], "broker", rbac["a_email"])
    response = app_client.get(f"/clients/{rbac['client_b']}")
    assert response.status_code == 404


def test_broker_cannot_edit_other_client(rbac, app_client):
    _session(app_client, rbac["a"], "broker", rbac["a_email"])
    response = app_client.post(
        f"/clients/{rbac['client_b']}/edit",
        data={"name": "Hacked", "phone": "01000000000", "csrf_token": CSRF},
    )
    assert response.status_code == 404
    assert _client_row(rbac["portal"], rbac["client_b"])["name"] == "Broker B Client"


def test_broker_cannot_change_other_client_status(rbac, app_client):
    _session(app_client, rbac["a"], "broker", rbac["a_email"])
    response = app_client.post(
        f"/clients/{rbac['client_b']}/status",
        data={"status": "Closed", "csrf_token": CSRF},
    )
    assert response.status_code == 404
    assert _client_row(rbac["portal"], rbac["client_b"])["status"] == "Pending"


def test_broker_cannot_complete_other_followup(rbac, app_client):
    _session(app_client, rbac["a"], "broker", rbac["a_email"])
    response = app_client.post(
        f"/clients/{rbac['client_b']}/complete-followup",
        data={"note": "x", "csrf_token": CSRF},
    )
    assert response.status_code == 404
    assert _client_row(rbac["portal"], rbac["client_b"])["followup_at"] is not None


def test_broker_cannot_add_activity_to_other_client(rbac, app_client):
    _session(app_client, rbac["a"], "broker", rbac["a_email"])
    before = _count(
        rbac["portal"], "SELECT COUNT(*) FROM activities WHERE client_id=?", (rbac["client_b"],)
    )
    response = app_client.post(
        f"/clients/{rbac['client_b']}/activity",
        data={"body": "intrusion", "activity_type": "Note", "csrf_token": CSRF},
    )
    assert response.status_code == 404
    after = _count(
        rbac["portal"], "SELECT COUNT(*) FROM activities WHERE client_id=?", (rbac["client_b"],)
    )
    assert after == before


def test_broker_cannot_create_opportunity_for_other_client(rbac, app_client):
    _session(app_client, rbac["a"], "broker", rbac["a_email"])
    response = app_client.post(
        f"/clients/{rbac['client_b']}/opportunity",
        data={"project": "Intrusion", "offered_price": "1", "csrf_token": CSRF},
    )
    assert response.status_code == 404
    assert (
        _count(
            rbac["portal"],
            "SELECT COUNT(*) FROM opportunities WHERE client_id=?",
            (rbac["client_b"],),
        )
        == 0
    )


def test_broker_cannot_update_other_opportunity_status(rbac, app_client):
    conn = rbac["portal"].db()
    try:
        cur = conn.execute(
            "INSERT INTO opportunities(client_id,project,offered_price,status,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?)",
            (rbac["client_b"], "B Opp", "1", "New", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        opp_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    _session(app_client, rbac["a"], "broker", rbac["a_email"])
    response = app_client.post(
        f"/opportunities/{opp_id}/status",
        data={"status": "Won", "csrf_token": CSRF},
    )
    assert response.status_code == 404
    conn = rbac["portal"].db()
    try:
        status = conn.execute("SELECT status FROM opportunities WHERE id=?", (opp_id,)).fetchone()[0]
    finally:
        conn.close()
    assert status == "New"


def test_broker_cannot_reassign_own_client_via_hidden_field(rbac, app_client):
    _session(app_client, rbac["a"], "broker", rbac["a_email"])
    response = app_client.post(
        f"/clients/{rbac['client_a']}/edit",
        data={
            "name": "Broker A Client",
            "phone": "01000000000",
            "assigned_to": str(rbac["b"]),
            "csrf_token": CSRF,
        },
    )
    assert response.status_code == 302
    row = _client_row(rbac["portal"], rbac["client_a"])
    assert row["assigned_to"] == rbac["a"]
    assert row["broker_id"] == rbac["a"]


def test_broker_add_client_cannot_assign_to_another_broker(rbac, app_client):
    _session(app_client, rbac["a"], "broker", rbac["a_email"])
    phone = "0100" + uuid.uuid4().hex[:7]
    response = app_client.post(
        "/clients/add",
        data={
            "name": "Forged Owner Client",
            "phone": phone,
            "assigned_to": str(rbac["b"]),
            "csrf_token": CSRF,
        },
    )
    assert response.status_code == 302
    conn = rbac["portal"].db()
    try:
        row = conn.execute(
            "SELECT assigned_to,broker_id FROM clients WHERE phone=?", (phone,)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["assigned_to"] == rbac["a"]
    assert row["broker_id"] == rbac["a"]


def test_broker_cannot_see_other_broker_clients_in_search(rbac, app_client):
    _session(app_client, rbac["a"], "broker", rbac["a_email"])
    response = app_client.get("/api/search?q=Broker%20B%20Client")
    assert response.status_code == 200
    payload = response.get_json()
    client_urls = [r["url"] for r in payload["results"] if r["kind"] == "Client"]
    assert all(f"/clients/{rbac['client_b']}" not in url for url in client_urls)


def test_broker_cannot_see_other_broker_clients_in_list(rbac, app_client):
    _session(app_client, rbac["a"], "broker", rbac["a_email"])
    response = app_client.get("/clients")
    assert response.status_code == 200
    assert b"Broker A Client" in response.data
    assert b"Broker B Client" not in response.data


# ---------------------------------------------------------------- admin

def test_admin_can_access_other_brokers_client(rbac, admin_client):
    response = admin_client.get(f"/clients/{rbac['client_b']}")
    assert response.status_code == 200
    assert b"Broker B Client" in response.data


def test_broker_cannot_access_admin_endpoints(rbac, app_client, live_version):
    _session(app_client, rbac["a"], "broker", rbac["a_email"])

    for path in ("/admin", "/admin/audit"):
        response = app_client.get(path)
        assert response.status_code == 403, path

    response = app_client.get(f"/admin/version/{live_version}")
    assert response.status_code == 403

    response = app_client.post(
        "/admin/users",
        data={"action": "create", "email": "x@test", "password": "Abcdef12345", "csrf_token": CSRF},
    )
    assert response.status_code == 403

    response = app_client.post(f"/admin/version/{live_version}/publish", data={"csrf_token": CSRF})
    assert response.status_code == 403


# ---------------------------------------------------------------- shared data

def _live_listing_id(portal, version_id):
    conn = portal.db()
    try:
        row = conn.execute(
            "SELECT id FROM listings WHERE version_id=? ORDER BY id LIMIT 1", (version_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return row["id"]


def test_broker_can_read_shared_inventory(rbac, app_client, live_version):
    _session(app_client, rbac["a"], "broker", rbac["a_email"])
    listing_id = _live_listing_id(rbac["portal"], live_version)

    assert app_client.get("/projects").status_code == 200
    assert app_client.get(f"/listing/{listing_id}").status_code == 200
    assert app_client.get("/api/search?q=October").status_code == 200


def test_broker_cannot_modify_shared_inventory(rbac, app_client, live_version):
    _session(app_client, rbac["a"], "broker", rbac["a_email"])
    listing_id = _live_listing_id(rbac["portal"], live_version)

    conn = rbac["portal"].db()
    try:
        before = dict(conn.execute("SELECT developer,project FROM listings WHERE id=?", (listing_id,)).fetchone())
    finally:
        conn.close()

    assert app_client.get(f"/listing/{listing_id}/edit").status_code == 403
    assert (
        app_client.post(
            f"/listing/{listing_id}/edit",
            data={"developer": "HACKED", "csrf_token": CSRF},
        ).status_code
        == 403
    )
    assert (
        app_client.post(
            f"/listing/{listing_id}/reset-override", data={"csrf_token": CSRF}
        ).status_code
        == 403
    )
    assert (
        app_client.post(
            f"/admin/listings/{listing_id}/delete", data={"csrf_token": CSRF}
        ).status_code
        == 403
    )
    assert app_client.post("/admin/upload", data={"csrf_token": CSRF}).status_code == 403

    conn = rbac["portal"].db()
    try:
        row = conn.execute("SELECT developer,project FROM listings WHERE id=?", (listing_id,)).fetchone()
    finally:
        conn.close()
    assert row is not None, "listing must not be deleted"
    assert dict(row) == before


# ---------------------------------------------------------------- ownership preserved

def test_ownership_fields_unchanged_after_denied_requests(rbac, app_client):
    _session(app_client, rbac["a"], "broker", rbac["a_email"])
    before = {
        k: _client_row(rbac["portal"], rbac["client_b"])[k]
        for k in ("assigned_to", "broker_id", "created_by")
    }

    app_client.get(f"/clients/{rbac['client_b']}")
    app_client.post(
        f"/clients/{rbac['client_b']}/edit",
        data={"name": "x", "phone": "1", "csrf_token": CSRF},
    )
    app_client.post(
        f"/clients/{rbac['client_b']}/status",
        data={"status": "Closed", "csrf_token": CSRF},
    )
    app_client.post(
        f"/clients/{rbac['client_b']}/activity",
        data={"body": "x", "csrf_token": CSRF},
    )

    after = {
        k: _client_row(rbac["portal"], rbac["client_b"])[k]
        for k in ("assigned_to", "broker_id", "created_by")
    }
    assert after == before
