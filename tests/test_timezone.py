from zoneinfo import ZoneInfo


def test_cairo_timezone_loads(portal):
    # This is the guard for the Windows tzdata dependency.
    assert ZoneInfo("Africa/Cairo") is not None
    assert portal.CAIRO_TZ.key == "Africa/Cairo"


def test_display_dt_treats_naive_values_as_utc(portal):
    # 20 Nov 2026 is outside Egypt's DST window, so Cairo is UTC+2.
    assert portal.display_dt("2026-11-20T10:00:00") == "20 Nov 2026 · 12:00 PM"


def test_cairo_now_is_timezone_aware(portal):
    now = portal.cairo_now()
    assert now.tzinfo is not None
    assert now.utcoffset() is not None
