EXPECTED_TABLES = {
    "users",
    "versions",
    "manual_projects",
    "listings",
    "clients",
    "opportunities",
    "activities",
    "favorites",
    "audit_logs",
    "update_intelligence",
}


def _schema(portal):
    conn = portal.db()
    try:
        rows = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return {row["name"]: row["sql"] for row in rows}
    finally:
        conn.close()


def test_expected_tables_exist(portal):
    assert EXPECTED_TABLES <= set(_schema(portal))


def test_init_db_is_idempotent(portal):
    before = _schema(portal)
    portal.init_db()
    after = _schema(portal)
    assert before == after
