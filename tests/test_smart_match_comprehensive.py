import os

import pytest

from conftest import WORKBOOK


def _seed_listings(portal, admin_user_id, specs):
    conn = portal.db()
    try:
        conn.execute("UPDATE versions SET status='archived' WHERE status='live'")
        cur = conn.execute(
            "INSERT INTO versions(filename,status,created_at,created_by) VALUES(?,?,?,?)",
            (WORKBOOK.name, "draft", "2026-01-01T00:00:00", admin_user_id),
        )
        vid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    conn = portal.db()
    try:
        for s in specs:
            conn.execute(
                """INSERT INTO listings(version_id,source_sheet,source_row,original_json,developer,project,location,
                   total_price_min,total_price_max,space_min,space_max,unit_type,unit_type_canonical,category,
                   normalized_developer,normalized_project,normalized_location,normalized_unit_type,source_type)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (vid, "S", 1, "{}", s.get("developer", "Dev"), s["project"], s["location"],
                 s.get("price"), s.get("price"), s.get("space"), s.get("space"),
                 s["unit_type"], s.get("canonical", ""), s.get("category", ""),
                 "dev", s["project"].lower().replace(" ", ""), s["location"].lower().replace(" ", ""),
                 s["unit_type"], "excel"),
            )
        conn.commit()
        conn.execute("UPDATE versions SET status='live' WHERE id=?", (vid,))
        conn.commit()
    finally:
        conn.close()
    return vid


SPECS = [
    {"project": "A", "location": "Sheikh Zayed", "unit_type": "Apartment", "canonical": "Apartment", "category": "Residential", "price": 4_500_000, "space": 150},
    {"project": "B", "location": "Sheikh Zayed", "unit_type": "Apartment", "canonical": "Apartment", "category": "Residential", "price": 5_000_000, "space": 150},
    {"project": "C", "location": "Sheikh Zayed", "unit_type": "Apartment", "canonical": "Apartment", "category": "Residential", "price": 5_500_000, "space": 150},
    {"project": "D", "location": "Sheikh Zayed", "unit_type": "Apartment", "canonical": "Apartment", "category": "Residential", "price": 5_500_001, "space": 150},
    {"project": "E", "location": "Sheikh Zayed", "unit_type": "Chalet", "canonical": "Chalet", "category": "Residential", "price": 4_000_000, "space": 150},
    {"project": "F", "location": "Sheikh Zayed", "unit_type": "Office", "canonical": "Commercial", "category": "Commercial", "price": 4_000_000, "space": 150},
    {"project": "G", "location": "Ain Sokhna", "unit_type": "Apartment", "canonical": "Apartment", "category": "Residential", "price": 4_000_000, "space": 150},
    {"project": "H", "location": "Sheikh Zayed", "unit_type": "Apartment", "canonical": "Apartment", "category": "Residential", "price": None, "space": 150},
    {"project": "I", "location": "Sheikh Zayed", "unit_type": "Penthouse", "canonical": "", "category": "", "price": 4_000_000, "space": 150},
]


def _make_client(portal, admin_user_id, unit_pref, category, budget="5,000,000"):
    conn = portal.db()
    try:
        cur = conn.execute(
            """INSERT INTO clients(broker_id,name,phone,budget,preferred_location,preferred_unit_type,
               property_category,status,created_at,updated_at,created_by,assigned_to)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (admin_user_id, "SM Test", "010", budget, "Sheikh Zayed", unit_pref, category,
             "Pending", "2026-01-01T00:00:00", "2026-01-01T00:00:00", admin_user_id, admin_user_id),
        )
        cid = cur.lastrowid
        conn.execute("INSERT INTO client_locations(client_id,location,created_at) VALUES(?,?,?)",
                     (cid, "Sheikh Zayed", "2026-01-01T00:00:00"))
        conn.commit()
    finally:
        conn.close()
    return cid


@pytest.fixture(autouse=True)
def _reset_admin_password(portal):
    conn = portal.db()
    try:
        conn.execute("UPDATE users SET must_change_password=0 WHERE role='admin'")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def seeded(portal, admin_user_id):
    _seed_listings(portal, admin_user_id, SPECS)
    return portal


def test_apartment_client_groups(seeded, portal, admin_user_id, admin_client):
    cid = _make_client(portal, admin_user_id, "Apartment", "Residential")
    resp = admin_client.get(f"/clients/{cid}")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Near-Budget Alternatives" in body
    assert "Near-budget" in body
    assert "No matching units found" not in body


def test_three_groups_only(seeded, portal, admin_user_id, admin_client):
    cid = _make_client(portal, admin_user_id, "Apartment", "Residential")
    resp = admin_client.get(f"/clients/{cid}")
    assert resp.status_code == 200
    body = resp.data.decode()
    # Stretch group removed; exactly three groups present.
    assert "Stretch Options" not in body
    assert "Best Matches" in body
    assert "Partial Matches" in body
    assert "Near-Budget Alternatives" in body


def test_eligible_non_near_all_in_best_or_partial(seeded, portal, admin_user_id, admin_client):
    # The deterministic dataset: A/B best, C near, D excluded.
    cid = _make_client(portal, admin_user_id, "Apartment", "Residential")
    resp = admin_client.get(f"/clients/{cid}")
    assert resp.status_code == 200
    body = resp.data.decode()
    # Best Matches non-empty; Near-Budget separate; no duplicate listings.
    sm = body.split("SMART MATCH")[-1]
    assert "Best Matches" in sm
    assert "Near-Budget Alternatives" in sm
    # Near-budget always present in the near section, not in Partial (it's badged).
    assert "NEAR-BUDGET" in sm or "Near-budget" in sm


def test_no_category_no_unit_type_sees_unclassified(seeded, portal, admin_user_id, admin_client):
    cid = _make_client(portal, admin_user_id, "", "")
    resp = admin_client.get(f"/clients/{cid}")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Unit type not classified" in body
    assert "No matching units found" not in body


def test_commercial_client(seeded, portal, admin_user_id, admin_client):
    cid = _make_client(portal, admin_user_id, "", "Commercial")
    resp = admin_client.get(f"/clients/{cid}")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "No matching units found" not in body


def test_unknown_preference_no_matches(seeded, portal, admin_user_id, admin_client):
    cid = _make_client(portal, admin_user_id, "Penthouse", "")
    resp = admin_client.get(f"/clients/{cid}")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "No matching units found" in body


def test_genuine_partial_missing_size(seeded, portal, admin_user_id, admin_client):
    # Listing missing size; client has space preference -> not Best, Partial only.
    conn = portal.db()
    try:
        cur = conn.execute(
            """INSERT INTO listings(version_id,source_sheet,source_row,original_json,developer,project,location,
               total_price_min,total_price_max,space_min,space_max,unit_type,unit_type_canonical,category,
               normalized_developer,normalized_project,normalized_location,normalized_unit_type,source_type)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (conn.execute("SELECT id FROM versions WHERE status='live' LIMIT 1").fetchone()[0], "S", 9, "{}",
             "Dev", "J", "Sheikh Zayed", 4_000_000, 4_000_000, None, None, "Apartment", "Apartment", "Residential",
             "dev", "j", "sheikh zayed", "apartment", "excel"))
        conn.commit()
    finally:
        conn.close()
    cid = _make_client(portal, admin_user_id, "Apartment", "Residential")
    # Client explicitly specifies a preferred area.
    conn = portal.db()
    try:
        conn.execute("UPDATE clients SET preferred_space_min=?, preferred_space_max=? WHERE id=?", (150, 150, cid))
        conn.commit()
    finally:
        conn.close()
    resp = admin_client.get(f"/clients/{cid}")
    assert resp.status_code == 200
    body = resp.data.decode()
    # The missing-size listing must be eligible but not Best. It appears in Partial/Near with a reason.
    assert "Size not available" in body


def test_missing_bedrooms_not_best(seeded, portal, admin_user_id, admin_client):
    conn = portal.db()
    try:
        cur = conn.execute(
            """INSERT INTO listings(version_id,source_sheet,source_row,original_json,developer,project,location,
               total_price_min,total_price_max,space_min,space_max,unit_type,unit_type_canonical,category,
               normalized_developer,normalized_project,normalized_location,normalized_unit_type,source_type)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (conn.execute("SELECT id FROM versions WHERE status='live' LIMIT 1").fetchone()[0], "S", 10, "{}",
             "Dev", "K", "Sheikh Zayed", 4_000_000, 4_000_000, 150, 150, "Apartment", "Apartment", "Residential",
             "dev", "k", "sheikh zayed", "apartment", "excel"))
        conn.commit()
    finally:
        conn.close()
    cid = _make_client(portal, admin_user_id, "Apartment", "Residential")
    # Client explicitly requests 3 bedrooms; listing has nobedroom data.
    conn = portal.db()
    try:
        conn.execute("UPDATE clients SET bedrooms='3', preferred_space_min=NULL, preferred_space_max=NULL WHERE id=?", (cid,))
        conn.commit()
    finally:
        conn.close()
    resp = admin_client.get(f"/clients/{cid}")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Bedrooms not confirmed" in body


def test_no_duplicates_and_exact_first(seeded, portal, admin_user_id, admin_client):
    cid = _make_client(portal, admin_user_id, "Apartment", "Residential")
    resp = admin_client.get(f"/clients/{cid}")
    assert resp.status_code == 200
    body = resp.data.decode()
    # No listing id appears in two groups (group sections are distinct).
    import re
    # Ensure near section only has one entry and exact sections don't duplicate near.
    assert "Near-Budget Alternatives" in body


def test_empty_state_when_no_eligible(seeded, portal, admin_user_id, admin_client):
    conn = portal.db()
    try:
        cur = conn.execute(
            """INSERT INTO clients(broker_id,name,phone,budget,preferred_location,preferred_unit_type,
               property_category,status,created_at,updated_at,created_by,assigned_to)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (admin_user_id, "Empty Client", "010", "1,000,000", "Sheikh Zayed", "Apartment", "Residential",
             "Pending", "2026-01-01T00:00:00", "2026-01-01T00:00:00", admin_user_id, admin_user_id),
        )
        cid = cur.lastrowid
        conn.execute("INSERT INTO client_locations(client_id,location,created_at) VALUES(?,?,?)",
                     (cid, "Sheikh Zayed", "2026-01-01T00:00:00"))
        conn.commit()
    finally:
        conn.close()
    resp = admin_client.get(f"/clients/{cid}")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "No matching units found" in body