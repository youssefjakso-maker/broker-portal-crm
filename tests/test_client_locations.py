import pytest


def test_client_multi_location_persisted(admin_client, portal):
    resp = admin_client.post(
        "/clients/add",
        data={
            "csrf_token": "test-csrf-token",
            "name": "Multi Loc Client",
            "phone": "01000000001",
            "property_category": "Residential",
            "budget": "5,000,000",
            "preferred_locations": ["Sheikh Zayed", "6 October"],
            "preferred_locations_text": "New Zayed",
            "preferred_unit_type": "Apartment",
            "priority": "High",
        },
    )
    assert resp.status_code in (200, 302)
    conn = portal.db()
    try:
        row = conn.execute(
            "SELECT id FROM clients WHERE name='Multi Loc Client' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        cid = row["id"]
        locs = [r["location"] for r in conn.execute(
            "SELECT location FROM client_locations WHERE client_id=?", (cid,)
        ).fetchall()]
        assert set(locs) == {"Sheikh Zayed", "6 October", "New Zayed"}
        cat = conn.execute(
            "SELECT property_category, priority, budget FROM clients WHERE id=?", (cid,)
        ).fetchone()
        assert cat["property_category"] == "Residential"
        assert cat["priority"] == "High"
        assert cat["budget"] == "5,000,000"
    finally:
        conn.close()


def test_client_detail_renders_locations(admin_client, portal):
    conn = portal.db()
    try:
        row = conn.execute(
            "SELECT id FROM clients WHERE name='Multi Loc Client' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        cid = row["id"]
    finally:
        conn.close()
    resp = admin_client.get(f"/clients/{cid}")
    assert resp.status_code == 200
    body = resp.data
    assert b"Sheikh Zayed" in body
    assert b"6 October" in body
    assert b"Total Budget (EGP)" in body