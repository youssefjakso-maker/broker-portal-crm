"""RBAC isolation tests (new for P1.7 audit).

Verifies a Broker cannot access/mutate another Broker's private clients,
and that Brokers are locked out of Admin pages. Server-side checks only;
no UI reliance.
"""
import pytest


def _mk_broker(portal, email):
    from werkzeug.security import generate_password_hash
    import uuid
    conn = portal.db()
    try:
        uniq = uuid.uuid4().hex[:8]
        email = f"{email.split('@')[0]}{uniq}@{email.split('@')[1]}"
        cur = conn.execute(
            "INSERT INTO users(email,password_hash,role,active,created_at) VALUES(?,?,?,?,?)",
            (email, generate_password_hash("Broker123456"), "broker", 1, "2026-01-01T00:00:00"),
        )
        uid = cur.lastrowid
        conn.commit()
        return uid
    finally:
        conn.close()


def _mk_client(portal, owner_uid, name):
    conn = portal.db()
    try:
        cur = conn.execute(
            """INSERT INTO clients(broker_id,assigned_to,name,phone,status,created_at,updated_at,created_by)
               VALUES(?,?,?,?,?,?,?,?)""",
            (owner_uid, owner_uid, name, "01009999999", "Pending", "2026-01-01T00:00:00", "2026-01-01T00:00:00", owner_uid),
        )
        cid = cur.lastrowid
        conn.commit()
        return cid
    finally:
        conn.close()


def _login(client, uid, email):
    with client.session_transaction() as s:
        s["user_id"] = uid
        s["role"] = "broker"
        s["email"] = email
        s["_csrf"] = "test-csrf-token"


@pytest.fixture()
def rbac(portal, admin_user_id):
    bA = _mk_broker(portal, "brokerA@test")
    bB = _mk_broker(portal, "brokerB@test")
    client_b = _mk_client(portal, bB, "Broker B Client")
    return portal, admin_user_id, bA, bB, client_b


def test_broker_cannot_view_other_brokers_client(rbac, app_client):
    portal, admin, bA, bB, client_b = rbac
    _login(app_client, bA, "brokerA@test")
    assert app_client.get(f"/clients/{client_b}").status_code == 404


def test_broker_cannot_edit_other_brokers_client(rbac, app_client):
    portal, admin, bA, bB, client_b = rbac
    _login(app_client, bA, "brokerA@test")
    r = app_client.post(f"/clients/{client_b}/edit", data={"csrf_token": "test-csrf-token", "name": "Hacked"})
    assert r.status_code in (400, 404)
    # confirm unchanged
    conn = portal.db()
    try:
        name = conn.execute("SELECT name FROM clients WHERE id=?", (client_b,)).fetchone()["name"]
    finally:
        conn.close()
    assert name == "Broker B Client"


def test_broker_cannot_delete_other_brokers_client(rbac, app_client):
    portal, admin, bA, bB, client_b = rbac
    _login(app_client, bA, "brokerA@test")
    r = app_client.post(f"/clients/{client_b}/delete", data={"csrf_token": "test-csrf-token"})
    assert r.status_code == 403
    conn = portal.db()
    try:
        n = conn.execute("SELECT COUNT(*) FROM clients WHERE id=?", (client_b,)).fetchone()[0]
    finally:
        conn.close()
    assert n == 1


def test_broker_cannot_change_status_other_client(rbac, app_client):
    portal, admin, bA, bB, client_b = rbac
    _login(app_client, bA, "brokerA@test")
    r = app_client.post(f"/clients/{client_b}/status", data={"csrf_token": "test-csrf-token", "status": "Closed"})
    assert r.status_code in (400, 404)


def test_broker_cannot_add_activity_other_client(rbac, app_client):
    portal, admin, bA, bB, client_b = rbac
    _login(app_client, bA, "brokerA@test")
    r = app_client.post(f"/clients/{client_b}/activity", data={"csrf_token": "test-csrf-token", "body": "x", "activity_type": "Note"})
    assert r.status_code in (400, 404)


def test_broker_cannot_add_opportunity_other_client(rbac, app_client):
    portal, admin, bA, bB, client_b = rbac
    _login(app_client, bA, "brokerA@test")
    r = app_client.post(f"/clients/{client_b}/opportunity", data={"csrf_token": "test-csrf-token"})
    assert r.status_code in (400, 404)


def test_broker_cannot_complete_followup_other_client(rbac, app_client):
    portal, admin, bA, bB, client_b = rbac
    _login(app_client, bA, "brokerA@test")
    r = app_client.post(f"/clients/{client_b}/complete-followup", data={"csrf_token": "test-csrf-token", "note": "x"})
    assert r.status_code in (400, 404)


def test_broker_cannot_admin_routes(rbac, app_client):
    portal, admin, bA, bB, client_b = rbac
    _login(app_client, bA, "brokerA@test")
    for path in ("/admin", "/admin/audit", "/admin/upload", "/admin/users", "/admin/version/1", "/admin/projects/new"):
        r = app_client.get(path)
        assert r.status_code in (302, 403, 404, 405), f"{path} -> {r.status_code}"
        # POSTs to admin POST endpoints
        r2 = app_client.post(path, data={"csrf_token": "test-csrf-token"})
        assert r2.status_code in (302, 400, 403, 404, 405), f"{path} -> {r2.status_code}"


def test_api_search_no_other_brokers_clients(rbac, app_client):
    portal, admin, bA, bB, client_b = rbac
    conn = portal.db()
    try:
        # give broker B client a name token that would match search
        conn.execute("UPDATE clients SET name='BROKERBESTBEST' WHERE id=?", (client_b,))
        conn.commit()
    finally:
        conn.close()
    _login(app_client, bA, "brokerA@test")
    r = app_client.get("/api/search?q=BROKERBEST")
    assert r.status_code == 200
    import json as _json
    data = _json.loads(r.data)
    assert not any("BROKERBESTBEST" in x.get("title","") for x in data.get("results", [])), "should not leak other broker's client"
    # admin sees it
    _login(app_client, admin, "admin@local")
    r2 = app_client.get("/api/search?q=BROKERBEST")
    data2 = _json.loads(r2.data)
    assert any("BROKERBESTBEST" in x.get("title","") for x in data2.get("results", []))
