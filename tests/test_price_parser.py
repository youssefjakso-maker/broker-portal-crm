import app


def test_propagate_shared_trailing_unit():
    assert app.split_numeric_range("1.5 - 2.0 M", "price") == (1500000.0, 2000000.0, None)
    assert app.split_numeric_range("1.5 - 2.0M", "price") == (1500000.0, 2000000.0, None)


def test_propagate_trailing_unit_to_leading_unitless():
    assert app.split_numeric_range("1.5M - 2", "price") == (1500000.0, 2000000.0, None)
    assert app.split_numeric_range("1.5 - 2M", "price") == (1500000.0, 2000000.0, None)


def test_explicit_units_preserved_independently():
    assert app.split_numeric_range("500K - 2M", "price") == (500000.0, 2000000.0, None)
    assert app.split_numeric_range("1M - 2K", "price") == (2000.0, 1000000.0, None)


def test_no_propagation_for_mixed_explicit_units():
    # both have explicit (different) units -> no propagation, each preserved
    a, b, err = app.split_numeric_range("500K - 2M", "price")
    assert (a, b) == (500000.0, 2000000.0)


def test_malformed_suffixes_rejected():
    for raw in ("12m2", "5MX", "abc5Mdef"):
        a, b, err = app.split_numeric_range(raw, "price")
        assert a is None and b is None and err is not None


def test_currency_label_accepted():
    assert app.split_numeric_range("EGP 5,000,000", "price") == (5000000.0, 5000000.0, None)


def test_status_values_not_parsed():
    for raw in ("sold", "no info", "tba", "call for price", "-"):
        a, b, err = app.split_numeric_range(raw, "price")
        assert a is None and b is None


def test_wide_range_preserved():
    a, b, err = app.split_numeric_range("7.8M-61M", "price")
    assert (a, b) == (7800000.0, 61000000.0)


def test_empty_returns_none():
    assert app.split_numeric_range("", "price") == (None, None, None)
    assert app.split_numeric_range(None, "price") == (None, None, None)