import hashlib

# SHA-256 of the bundled source workbook at the start of the Phase 0/1 work.
# If this changes, the source data was modified and must be restored from backup.
ORIGINAL_WORKBOOK_SHA256 = (
    "3BBEC06F12CADFBDAA446E93D3ED0E11DCA552067564A15B4A07021540B0F59B"
)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_bundled_workbook_imports_without_errors(
    portal, imported_version, workbook_path
):
    before = _sha256(workbook_path)

    conn = portal.db()
    try:
        version = conn.execute(
            "SELECT * FROM versions WHERE id=?", (imported_version,)
        ).fetchone()
        listing_count = conn.execute(
            "SELECT COUNT(*) FROM listings WHERE version_id=?", (imported_version,)
        ).fetchone()[0]
    finally:
        conn.close()

    assert version["total_rows"] == 218
    assert version["imported_rows"] == 218
    assert version["serious_errors"] == 0
    assert listing_count == 218
    assert _sha256(workbook_path) == before


def test_source_workbook_is_unchanged(workbook_path):
    assert _sha256(workbook_path).upper() == ORIGINAL_WORKBOOK_SHA256
