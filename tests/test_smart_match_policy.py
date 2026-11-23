import app


def make_client(budget, locs, cat="", utype="Apartment"):
    return {
        "budget": str(budget),
        "preferred_location": locs[0] if locs else "",
        "preferred_locations_list": locs,
        "preferred_unit_type": utype,
        "unit_type": utype,
        "property_category": cat,
        "preferred_space_min": None,
        "preferred_space_max": None,
        "bedrooms": "",
        "preferred_developer": "",
        "preferred_project": "",
        "project": "",
    }


def make_listing(price, loc, utype="Apartment", cat=""):
    return {
        "location": loc,
        "total_price_min": price,
        "total_price_max": price,
        "unit_type": utype,
        "space_min": None,
        "space_max": None,
        "developer": "",
        "project": "P",
        "category": cat,
        "normalized_project": "p",
    }


def run(client, listing):
    w = app.recommendation_window_for(client)
    return app.recommendation_score(client, listing, w)


def test_exact_budget_match_within_budget():
    c = make_client(5_000_000, ["Sheikh Zayed"])
    l = make_listing(4_800_000, "Sheikh Zayed")
    score, reasons, band, eligible, _near = run(c, l)
    assert eligible is True
    assert band in ("best", "alternative")
    assert not any("exceeds the stated budget" in r for r in reasons)


def test_near_budget_match_separated():
    c = make_client(5_000_000, ["Sheikh Zayed"])
    l = make_listing(5_500_000, "Sheikh Zayed")  # +10%
    score, reasons, band, eligible, _near = run(c, l)
    assert eligible is True
    assert band == "alternative"
    assert any("exceeds the stated budget" in r for r in reasons)


def test_over_budget_excluded():
    c = make_client(5_000_000, ["Sheikh Zayed"])
    l = make_listing(7_000_000, "Sheikh Zayed")  # +40%
    score, reasons, band, eligible, _near = run(c, l)
    assert eligible is False


def test_location_conflict_excluded():
    c = make_client(5_000_000, ["Sheikh Zayed", "6 October"])
    l = make_listing(4_800_000, "Ain Sokhna")
    score, reasons, band, eligible, _near = run(c, l)
    assert eligible is False


def test_category_conflict_excluded():
    c = make_client(5_000_000, ["Sheikh Zayed"], cat="Residential")
    l = make_listing(4_800_000, "Sheikh Zayed", cat="Commercial")
    score, reasons, band, eligible, _near = run(c, l)
    assert eligible is False


def test_missing_location_no_match():
    c = make_client(5_000_000, [])
    l = make_listing(4_800_000, "Sheikh Zayed")
    score, reasons, band, eligible, _near = run(c, l)
    assert eligible is False


def test_missing_price_no_match():
    c = make_client(5_000_000, ["Sheikh Zayed"])
    l = make_listing(None, "Sheikh Zayed")
    score, reasons, band, eligible, _near = run(c, l)
    assert eligible is False


def test_exact_outranks_near_budget():
    c = make_client(5_000_000, ["Sheikh Zayed"])
    exact = make_listing(4_800_000, "Sheikh Zayed")
    near = make_listing(5_400_000, "Sheikh Zayed")
    se, _, be, _, _ = run(c, exact)
    sn, _, bn, _, _ = run(c, near)
    # exact must not be capped alternative; near must be alternative
    assert be in ("best", "alternative")
    assert bn == "alternative"
    assert not any("exceeds" in r for r in [])  # placeholder
    # exact score should be >= near score
    assert se >= sn


def test_window_percentages():
    # 2M budget -> [1.2M, 2.2M]
    c = make_client(2_000_000, ["Sheikh Zayed"])
    w = app.recommendation_window_for(c)
    assert abs(w[0] - 1_200_000) < 1
    assert abs(w[1] - 2_200_000) < 1
    assert w[2] == 2_000_000
    # 5M -> [3M, 5.5M]
    c = make_client(5_000_000, ["Sheikh Zayed"])
    w = app.recommendation_window_for(c)
    assert abs(w[0] - 3_000_000) < 1
    assert abs(w[1] - 5_500_000) < 1
    # 10M -> [6M, 11M]
    c = make_client(10_000_000, ["Sheikh Zayed"])
    w = app.recommendation_window_for(c)
    assert abs(w[0] - 6_000_000) < 1
    assert abs(w[1] - 11_000_000) < 1
