"""P1.7.1 — broker_ownership_history schema foundation.

These tests run against the session-scoped temporary database created by
conftest. The real persistent database is never opened by the test suite.
"""

EXPECTED_COLUMNS = [
    ("id", "INTEGER", 0, 1),
    ("client_id", "INTEGER", 1, 0),
    ("previous_owner_id", "INTEGER", 0, 0),
    ("new_owner_id", "INTEGER", 1, 0),
    ("admin_id", "INTEGER", 1, 0),
    ("reason", "TEXT", 0, 0),
    ("created_at", "TEXT", 1, 0),
]

EXPECTED_FKS = {
    "client_id": ("clients", "id", "CASCADE"),
    "previous_owner_id": ("users", "id", "NO ACTION"),
    "new_owner_id": ("users", "id", "NO ACTION"),
    "admin_id": ("users", "id", "NO ACTION"),
}


def _columns(conn, table):
    return [
        (row["name"], (row["type"] or "").upper(), row["notnull"], row["pk"])
        for row in conn.execute(f"PRAGMA table_info({table})")
    ]


def _fks(conn, table):
    return {
        row["from"]: (row["table"], row["to"], row["on_delete"])
        for row in conn.execute(f"PRAGMA foreign_key_list({table})")
    }


def _rows(conn, sql):
    return [tuple(row) for row in conn.execute(sql).fetchall()]


def _run_init_db(portal, admin_user_id):
    """Run init_db again without disturbing the shared admin test session.

    init_db re-flags accounts that still use a shipped default password. The
    session-scoped admin_user_id fixture clears that flag so other tests can
    use admin_client, so restore it after the migration run.
    """
    conn = portal.db()
    try:
        flag = conn.execute(
            "SELECT must_change_password FROM users WHERE id=?", (admin_user_id,)
        ).fetchone()[0]
    finally:
        conn.close()

    portal.init_db()

    conn = portal.db()
    try:
        conn.execute(
            "UPDATE users SET must_change_password=? WHERE id=?", (flag, admin_user_id)
        )
        conn.commit()
    finally:
        conn.close()


def _any_listing_id(portal):
    conn = portal.db()
    try:
        row = conn.execute("SELECT id FROM listings ORDER BY id LIMIT 1").fetchone()
    finally:
        conn.close()
    assert row is not None, "fixture requires at least one imported listing"
    return row["id"]


def _ensure_client(portal, admin_user_id):
    conn = portal.db()
    try:
        row = conn.execute("SELECT id FROM clients ORDER BY id LIMIT 1").fetchone()
        if row:
            return row["id"]
        cur = conn.execute(
            "INSERT INTO clients(broker_id,assigned_to,name,phone,status,created_at,updated_at,created_by) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                admin_user_id,
                admin_user_id,
                "Ownership History Fixture",
                "01000000000",
                "Pending",
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:00",
                admin_user_id,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _ensure_favorite(portal, user_id, listing_id):
    conn = portal.db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO favorites(user_id,listing_id,created_at) VALUES(?,?,?)",
            (user_id, listing_id, "2026-01-01T00:00:00"),
        )
        conn.commit()
    finally:
        conn.close()


def _ensure_opportunity(portal, client_id, listing_id):
    conn = portal.db()
    try:
        exists = conn.execute(
            "SELECT id FROM opportunities WHERE client_id=? AND listing_id=?",
            (client_id, listing_id),
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO opportunities(client_id,listing_id,project,offered_price,status,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    client_id,
                    listing_id,
                    "Fixture Project",
                    "1",
                    "New",
                    "2026-01-01T00:00:00",
                    "2026-01-01T00:00:00",
                ),
            )
            conn.commit()
    finally:
        conn.close()


def test_ownership_history_table_exists(portal):
    conn = portal.db()
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='broker_ownership_history'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None


def test_ownership_history_required_columns(portal):
    conn = portal.db()
    try:
        actual = _columns(conn, "broker_ownership_history")
    finally:
        conn.close()
    assert actual == EXPECTED_COLUMNS


def test_ownership_history_foreign_keys(portal):
    conn = portal.db()
    try:
        actual = _fks(conn, "broker_ownership_history")
    finally:
        conn.close()
    assert actual == EXPECTED_FKS


def test_ownership_history_migration_is_idempotent(portal, admin_user_id):
    conn = portal.db()
    try:
        schema_before = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='broker_ownership_history'"
        ).fetchone()["sql"]
        count_before = conn.execute(
            "SELECT COUNT(*) FROM broker_ownership_history"
        ).fetchone()[0]
    finally:
        conn.close()

    _run_init_db(portal, admin_user_id)
    _run_init_db(portal, admin_user_id)

    conn = portal.db()
    try:
        schema_after = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='broker_ownership_history'"
        ).fetchone()["sql"]
        count_after = conn.execute(
            "SELECT COUNT(*) FROM broker_ownership_history"
        ).fetchone()[0]
    finally:
        conn.close()

    assert schema_after == schema_before
    assert count_after == count_before


def test_existing_client_ownership_unchanged(portal, admin_user_id):
    _ensure_client(portal, admin_user_id)
    # Warm-up run: init_db performs pre-existing derived backfills. The
    # invariant under test is that a further migration run changes nothing.
    _run_init_db(portal, admin_user_id)

    conn = portal.db()
    try:
        before = _rows(conn, "SELECT * FROM clients ORDER BY id")
        ownership_before = _rows(
            conn, "SELECT id,assigned_to,broker_id,created_by FROM clients ORDER BY id"
        )
    finally:
        conn.close()

    _run_init_db(portal, admin_user_id)

    conn = portal.db()
    try:
        after = _rows(conn, "SELECT * FROM clients ORDER BY id")
        ownership_after = _rows(
            conn, "SELECT id,assigned_to,broker_id,created_by FROM clients ORDER BY id"
        )
    finally:
        conn.close()

    assert after == before
    assert ownership_after == ownership_before
    assert all(row[1] is not None for row in ownership_after)


def test_existing_listings_unchanged(portal, admin_user_id, live_version):
    # Warm-up run so the imported rows have already received the pre-existing
    # derived backfills (category/unit_type_canonical/normalized fields).
    _run_init_db(portal, admin_user_id)

    conn = portal.db()
    try:
        before = _rows(conn, "SELECT * FROM listings ORDER BY id")
    finally:
        conn.close()

    _run_init_db(portal, admin_user_id)

    conn = portal.db()
    try:
        after = _rows(conn, "SELECT * FROM listings ORDER BY id")
    finally:
        conn.close()

    assert after == before
    assert len(after) > 0


def test_existing_favorites_unchanged(portal, admin_user_id, live_version):
    _ensure_favorite(portal, admin_user_id, _any_listing_id(portal))
    _run_init_db(portal, admin_user_id)

    conn = portal.db()
    try:
        before = _rows(conn, "SELECT * FROM favorites ORDER BY id")
    finally:
        conn.close()
    assert before, "fixture favorite was not created"

    _run_init_db(portal, admin_user_id)

    conn = portal.db()
    try:
        after = _rows(conn, "SELECT * FROM favorites ORDER BY id")
    finally:
        conn.close()

    assert after == before


def test_existing_opportunities_unchanged(portal, admin_user_id, live_version):
    client_id = _ensure_client(portal, admin_user_id)
    _ensure_opportunity(portal, client_id, _any_listing_id(portal))
    _run_init_db(portal, admin_user_id)

    conn = portal.db()
    try:
        before = _rows(conn, "SELECT * FROM opportunities ORDER BY id")
    finally:
        conn.close()
    assert before, "fixture opportunity was not created"

    _run_init_db(portal, admin_user_id)

    conn = portal.db()
    try:
        after = _rows(conn, "SELECT * FROM opportunities ORDER BY id")
    finally:
        conn.close()

    assert after == before


def test_migration_creates_no_fake_history_rows(portal, admin_user_id):
    _run_init_db(portal, admin_user_id)

    conn = portal.db()
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM broker_ownership_history"
        ).fetchone()[0]
    finally:
        conn.close()

    assert count == 0
