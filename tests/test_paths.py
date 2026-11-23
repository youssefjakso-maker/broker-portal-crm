import os
from pathlib import Path


def test_data_directory_is_isolated(portal):
    assert portal.DATA == Path(os.environ["BROKER_PORTAL_DATA"]).resolve()
    assert portal.UPLOADS == portal.DATA / "uploads"
    assert portal.DB == portal.DATA / "broker_portal.db"
    assert portal.DATA.exists()
    assert portal.UPLOADS.exists()


def test_default_data_directory_when_unset(portal, monkeypatch):
    monkeypatch.delenv("BROKER_PORTAL_DATA", raising=False)
    assert portal._resolve_data_dir() == portal.BASE / "data"


def test_override_is_resolved_to_an_absolute_path(portal, monkeypatch, tmp_path):
    target = tmp_path / "nested" / "data"
    monkeypatch.setenv("BROKER_PORTAL_DATA", str(target))
    assert portal._resolve_data_dir() == target.resolve()
