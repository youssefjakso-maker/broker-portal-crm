import hashlib
import os

import pytest

from conftest import WORKBOOK


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _make_version(portal, admin_user_id, status="draft", serious_errors=0, empty=False):
    conn = portal.db()
    try:
        cur = conn.execute(
            "INSERT INTO versions(filename,status,created_at,created_by,serious_errors) VALUES(?,?,?, ?,?)",
            (WORKBOOK.name, status, "2026-01-01T00:00:00", admin_user_id, serious_errors),
        )
        vid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    if not empty:
        portal.import_workbook(WORKBOOK, vid)
    # set serious_errors on the version row (import may reset it to 0)
    conn = portal.db()
    try:
        conn.execute("UPDATE versions SET serious_errors=? WHERE id=?", (serious_errors, vid))
        conn.commit()
    finally:
        conn.close()
    return vid


def _live_id(portal):
    conn = portal.db()
    try:
        r = conn.execute("SELECT id FROM versions WHERE status='live' ORDER BY id DESC LIMIT 1").fetchone()
        return r["id"] if r else None
    finally:
        conn.close()


def test_restore_valid_archived(portal, admin_user_id, admin_client):
    vid_a = _make_version(portal, admin_user_id, "draft")
    conn = portal.db()
    try:
        conn.execute("UPDATE versions SET status='archived' WHERE status='live'")
        conn.execute("UPDATE versions SET status='live' WHERE id=?", (vid_a,))
        conn.commit()
    finally:
        conn.close()

    vid_b = _make_version(portal, admin_user_id, "draft")
    # publish b
    admin_client.post(f"/admin/version/{vid_b}/publish", data={"csrf_token": "test-csrf-token"})

    # restore a
    before_live = _live_id(portal)
    assert before_live == vid_b
    resp = admin_client.post(f"/admin/version/{vid_a}/restore", data={"csrf_token": "test-csrf-token"})
    assert resp.status_code in (200, 302)
    assert _live_id(portal) == vid_a


def test_restore_draft_rejected(portal, admin_user_id, admin_client):
    vid = _make_version(portal, admin_user_id, "draft")
    live_before = _live_id(portal)
    resp = admin_client.post(f"/admin/version/{vid}/restore", data={"csrf_token": "test-csrf-token"})
    assert resp.status_code in (200, 302)
    assert _live_id(portal) == live_before  # unchanged


def test_restore_serious_errors_rejected(portal, admin_user_id, admin_client):
    vid = _make_version(portal, admin_user_id, "archived", serious_errors=3)
    live_before = _live_id(portal)
    resp = admin_client.post(f"/admin/version/{vid}/restore", data={"csrf_token": "test-csrf-token"})
    assert resp.status_code in (200, 302)
    assert _live_id(portal) == live_before


def test_restore_missing_version_404(portal, admin_user_id, admin_client):
    resp = admin_client.post("/admin/version/999999/restore", data={"csrf_token": "test-csrf-token"})
    assert resp.status_code == 404


def test_restore_already_live_noop(portal, admin_user_id, admin_client):
    vid = _make_version(portal, admin_user_id, "draft")
    conn = portal.db()
    try:
        conn.execute("UPDATE versions SET status='archived' WHERE status='live'")
        conn.execute("UPDATE versions SET status='live' WHERE id=?", (vid,))
        conn.commit()
    finally:
        conn.close()
    # audit count before
    conn = portal.db()
    try:
        before = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action='Restored inventory version'").fetchone()[0]
    finally:
        conn.close()
    resp = admin_client.post(f"/admin/version/{vid}/restore", data={"csrf_token": "test-csrf-token"})
    assert resp.status_code in (200, 302)
    conn = portal.db()
    try:
        after = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action='Restored inventory version'").fetchone()[0]
    finally:
        conn.close()
    assert after == before  # no new audit entry


def test_restore_repeated(portal, admin_user_id, admin_client):
    vid_a = _make_version(portal, admin_user_id, "draft")
    vid_b = _make_version(portal, admin_user_id, "draft")
    conn = portal.db()
    try:
        conn.execute("UPDATE versions SET status='archived' WHERE status='live'")
        conn.execute("UPDATE versions SET status='live' WHERE id=?", (vid_a,))
        conn.commit()
    finally:
        conn.close()
    admin_client.post(f"/admin/version/{vid_b}/publish", data={"csrf_token": "test-csrf-token"})
    # restore a, then b, then a
    admin_client.post(f"/admin/version/{vid_a}/restore", data={"csrf_token": "test-csrf-token"})
    assert _live_id(portal) == vid_a
    admin_client.post(f"/admin/version/{vid_b}/restore", data={"csrf_token": "test-csrf-token"})
    assert _live_id(portal) == vid_b
    admin_client.post(f"/admin/version/{vid_a}/restore", data={"csrf_token": "test-csrf-token"})
    assert _live_id(portal) == vid_a


def test_restore_empty_version(portal, admin_user_id, admin_client):
    vid = _make_version(portal, admin_user_id, "archived", empty=True)
    # make it archived (it already is) and ensure a live version exists
    conn = portal.db()
    try:
        if not conn.execute("SELECT 1 FROM versions WHERE status='live'").fetchone():
            # promote any other version to live
            other = conn.execute("SELECT id FROM versions WHERE id!=? LIMIT 1", (vid,)).fetchone()
            if other:
                conn.execute("UPDATE versions SET status='live' WHERE id=?", (other["id"],))
                conn.commit()
    finally:
        conn.close()
    resp = admin_client.post(f"/admin/version/{vid}/restore", data={"csrf_token": "test-csrf-token"})
    assert resp.status_code in (200, 302)
    assert _live_id(portal) == vid


def test_restore_preserves_references(portal, admin_user_id, admin_client):
    vid_a = _make_version(portal, admin_user_id, "draft")
    conn = portal.db()
    try:
        conn.execute("UPDATE versions SET status='archived' WHERE status='live'")
        conn.execute("UPDATE versions SET status='live' WHERE id=?", (vid_a,))
        conn.commit()
        listing = conn.execute("SELECT id FROM listings WHERE version_id=? LIMIT 1", (vid_a,)).fetchone()
        old_lid = listing["id"]
        conn.execute("INSERT INTO favorites(user_id,listing_id,created_at) VALUES(?,?,?)",
                     (admin_user_id, old_lid, "2026-01-01T00:00:00"))
        conn.commit()
    finally:
        conn.close()

    vid_b = _make_version(portal, admin_user_id, "draft")
    admin_client.post(f"/admin/version/{vid_b}/publish", data={"csrf_token": "test-csrf-token"})

    # restore a
    admin_client.post(f"/admin/version/{vid_a}/restore", data={"csrf_token": "test-csrf-token"})

    conn = portal.db()
    try:
        # version A listing row remains intact
        va = conn.execute("SELECT id FROM listings WHERE id=?", (old_lid,)).fetchone()
        n = conn.execute("SELECT COUNT(*) FROM listings WHERE version_id=?", (vid_a,)).fetchone()[0]
        # favorite still exists somewhere (re-pointed on publish, preserved on restore)
        fav_total = conn.execute("SELECT COUNT(*) FROM favorites").fetchone()[0]
    finally:
        conn.close()
    assert va is not None
    assert n > 0
    assert fav_total >= 1


def test_restore_admin_permission(app_client):
    # unauthenticated -> redirect to login
    resp = app_client.post("/admin/version/1/restore", data={"csrf_token": "x"})
    assert resp.status_code in (302, 400, 401, 403)


def test_restore_workbook_unchanged(portal, admin_user_id, admin_client):
    vid = _make_version(portal, admin_user_id, "archived")
    # ensure a live version exists
    conn = portal.db()
    try:
        if not conn.execute("SELECT 1 FROM versions WHERE status='live'").fetchone():
            other = conn.execute("SELECT id FROM versions WHERE id!=? LIMIT 1", (vid,)).fetchone()
            if other:
                conn.execute("UPDATE versions SET status='live' WHERE id=?", (other["id"],))
                conn.commit()
    finally:
        conn.close()
    admin_client.post(f"/admin/version/{vid}/restore", data={"csrf_token": "test-csrf-token"})
    assert _sha256(WORKBOOK).upper() == "3BBEC06F12CADFBDAA446E93D3ED0E11DCA552067564A15B4A07021540B0F59B"