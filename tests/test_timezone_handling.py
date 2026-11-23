import app


def test_cairo_to_utc_round_trip():
    utc, err = app.cairo_local_to_utc_naive("2026-06-15T14:30")
    assert err is None
    assert utc == "2026-06-15T11:30:00"
    assert app.utc_naive_to_cairo_local_str(utc) == "2026-06-15T14:30"


def test_followup_2330_cairo():
    utc, err = app.cairo_local_to_utc_naive("2026-06-15T23:30")
    assert err is None
    assert utc == "2026-06-15T20:30:00"
    assert app.display_dt(utc) == "15 Jun 2026 · 11:30 PM"


def test_followup_0030_cairo():
    utc, err = app.cairo_local_to_utc_naive("2026-06-15T00:30")
    assert err is None
    assert utc == "2026-06-14T21:30:00"
    # Cairo calendar date is preserved on display.
    assert app.display_dt(utc) == "15 Jun 2026 · 12:30 AM"


def test_invalid_format_rejected():
    utc, err = app.cairo_local_to_utc_naive("not-a-date")
    assert utc is None
    assert err is not None


def test_empty_returns_empty():
    utc, err = app.cairo_local_to_utc_naive("")
    assert utc == ""
    assert err is None


def test_cairo_day_bounds():
    s, e = app.cairo_day_utc_bounds("2026-06-15")
    # 2026-06-15 Cairo day -> 2026-06-14 21:00 UTC .. 2026-06-15 21:00 UTC
    assert s == "2026-06-14T21:00:00"
    assert e == "2026-06-15T21:00:00"


def test_display_dt_utc_to_cairo():
    assert app.display_dt("2026-06-15T11:30:00") == "15 Jun 2026 · 02:30 PM"


def test_cairo_input_filter_registered():
    assert "cairo_input" in app.app.jinja_env.filters


def test_nonexistent_spring_forward_rejected():
    # 2026-04-24 00:30 Cairo is in the spring-forward gap (does not exist).
    utc, err = app.cairo_local_to_utc_naive("2026-04-24T00:30")
    assert utc is None
    assert err is not None
    assert "ambiguous or invalid" in err


def test_ambiguous_fall_back_rejected():
    # 2026-10-29 23:30 Cairo is in the fall-back overlap (ambiguous).
    utc, err = app.cairo_local_to_utc_naive("2026-10-29T23:30")
    assert utc is None
    assert err is not None
    assert "ambiguous or invalid" in err


def test_dst_transition_dates_from_tzdata():
    # Confirm the installed tzdata actually has transitions on these dates.
    from zoneinfo import ZoneInfo
    from datetime import datetime, timedelta
    tz = ZoneInfo("Africa/Cairo")
    # spring forward: 2026-04-24 00:30 has differing fold offsets
    naive = datetime(2026, 4, 24, 0, 30)
    assert naive.replace(tzinfo=tz, fold=0).utcoffset() != naive.replace(tzinfo=tz, fold=1).utcoffset()
    # fall back: 2026-10-29 23:30 has differing fold offsets
    naive = datetime(2026, 10, 29, 23, 30)
    assert naive.replace(tzinfo=tz, fold=0).utcoffset() != naive.replace(tzinfo=tz, fold=1).utcoffset()