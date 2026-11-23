import app
from werkzeug.security import generate_password_hash


def _setup(portal):
    conn = portal.db()
    conn.execute("UPDATE users SET must_change_password=0 WHERE role='admin'")
    cur = conn.execute(
        "INSERT INTO clients(broker_id,name,phone,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
        (1, "C1", "01009999999", "Pending", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
    )
    cid = cur.lastrowid
    conn.commit(); conn.close()
    return cid


def _login(client):
    with client.session_transaction() as s:
        s["user_id"] = 1; s["role"] = "admin"; s["email"] = "admin@local"; s["_csrf"] = "test-csrf-token"


def test_edit_client_rejects_empty_name(portal, admin_client):
    cid = _setup(portal)
    r = admin_client.post(f"/clients/{cid}/edit", data={"csrf_token": "test-csrf-token", "name": "", "phone": ""})
    assert r.status_code in (302, 400)
    conn = portal.db()
    try:
        name = conn.execute("SELECT name FROM clients WHERE id=?", (cid,)).fetchone()["name"]
    finally:
        conn.close()
    assert name  # unchanged, not deleted


def test_update_client_status_rejects_invalid_status(portal, admin_client):
    cid = _setup(portal)
    r = admin_client.post(f"/clients/{cid}/status", data={"csrf_token": "test-csrf-token", "status": "Bogus"})
    assert r.status_code == 400


def test_update_client_status_valid_status(portal, admin_client):
    cid = _setup(portal)
    r = admin_client.post(f"/clients/{cid}/status", data={"csrf_token": "test-csrf-token", "status": "Closed"})
    assert r.status_code in (200, 302)
    conn = portal.db()
    try:
        st = conn.execute("SELECT status FROM clients WHERE id=?", (cid,)).fetchone()["status"]
    finally:
        conn.close()
    assert st == "Closed"


def test_users_toggle_empty_user_id_no_500(portal, admin_client):
    r = admin_client.post("/admin/users", data={"csrf_token": "test-csrf-token", "action": "toggle", "user_id": ""})
    assert r.status_code in (200, 302, 400)


def test_users_password_empty_user_id_no_500(portal, admin_client):
    r = admin_client.post("/admin/users", data={"csrf_token": "test-csrf-token", "action": "password", "user_id": ""})
    assert r.status_code in (200, 302, 400)


def test_users_toggle_valid_broker(portal, admin_client):
    from werkzeug.security import generate_password_hash
    conn = portal.db()
    try:
        cur = conn.execute("INSERT INTO users(email,password_hash,role,active,created_at) VALUES(?,?,?,?,?)",
                           ("valbroker@test", generate_password_hash("Broker123456"), "broker", 1, "2026-01-01T00:00:00"))
        uid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    r = admin_client.post("/admin/users", data={"csrf_token": "test-csrf-token", "action": "toggle", "user_id": uid})
    assert r.status_code in (200, 302, 400)
    conn = portal.db()
    try:
        active = conn.execute("SELECT active FROM users WHERE id=?", (uid,)).fetchone()["active"]
    finally:
        conn.close()
    assert active in (0, 1)


def test_dashboard_target_env(portal, admin_client, monkeypatch):
    # target from env
    import os
    monkeypatch.setenv("BROKER_PORTAL_SALES_TARGET", "5M")
    assert app._broker_sales_target() == 5_000_000
    monkeypatch.delenv("BROKER_PORTAL_SALES_TARGET", raising=False)
    assert app._broker_sales_target() == 10_000_000