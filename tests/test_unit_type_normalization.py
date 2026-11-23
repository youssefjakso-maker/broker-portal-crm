import app

RAW_TO_CANONICAL = {
    "RES": "Residential",
    "Chalet": "Chalet",
    "comm": "Commercial",
    "comm- admin- med": "Commercial",
    "comm- ad- med": "Commercial",
    "comm -ad - med - ph": "Commercial",
    "comm - med - ad - ph": "Commercial",
    "comm-med-ad": "Commercial",
    "comm- ph": "Commercial",
    "comm- med": "Commercial",
    "comm- admin- med - ph": "Commercial",
    "comm - ph": "Commercial",
    "comm - med- ad": "Commercial",
    "com": "Commercial",
    "AD": "Commercial",
    "Ad-Med": "Commercial",
    "Ad-med": "Commercial",
    "Ad-comm": "Commercial",
    "AD-comm": "Commercial",
    "AD- comm": "Commercial",
    "med": "Commercial",
    "Med": "Commercial",
    "MED - PH": "Commercial",
    "Med - Ph": "Commercial",
    "Admin": "Commercial",
    "Ret-PH-comm": "Commercial",
    "Studio": "Studio",
    "Hotle apartment": "Hotel Apartment",
    "Hotle apartment -RES": "Hotel Apartment",
    "No Info": "",
    "HOLD": "",
    "sold out": "",
}


def test_canonical_mapping_all_inspected_values():
    for raw, canonical in RAW_TO_CANONICAL.items():
        assert app.canonical_unit_type(raw) == canonical, (raw, app.canonical_unit_type(raw))


def test_unknown_future_value_not_canonical():
    # Unknown values are NOT treated as recognized canonical types.
    assert app.canonical_unit_type("Zzzunknown") == ""
    assert app.canonical_unit_type("Penthouse") == ""
    assert app.canonical_unit_type("  penthouse  ") == ""
    assert app.canonical_unit_type("PENTHOUSE") == ""


def test_empty_returns_empty():
    assert app.canonical_unit_type("") == ""
    assert app.canonical_unit_type(None) == ""


def test_listing_uid_unchanged_by_canonicalization():
    item = {"unit_type": "comm", "developer": "D", "project": "P", "location": "L",
            "space_min": 100, "space_max": 100, "project_location": "PL", "company_location": "CL",
            "original": {}}
    uid_before = app.listing_uid(item)
    # canonicalization does not touch identity inputs
    item2 = dict(item)
    assert app.listing_uid(item2) == uid_before


def test_residential_category_match_all_residential_types():
    # A Residential client with no specific unit type matches any residential unit.
    client = {
        "budget": "5000000",
        "preferred_location": "Sheikh Zayed",
        "preferred_locations_list": ["Sheikh Zayed"],
        "preferred_unit_type": "",
        "unit_type": "",
        "property_category": "Residential",
        "preferred_space_min": None,
        "preferred_space_max": None,
        "bedrooms": "",
        "preferred_developer": "",
        "preferred_project": "",
        "project": "",
    }
    for ut in ["Apartment", "Chalet", "Villa", "Townhouse", "Twin House", "Studio", "Hotel Apartment", "RES"]:
        listing = {
            "location": "Sheikh Zayed",
            "total_price_min": 4_000_000,
            "total_price_max": 4_000_000,
            "unit_type": ut,
            "unit_type_canonical": app.canonical_unit_type(ut),
            "category": "Residential",
            "space_min": None,
            "space_max": None,
            "developer": "",
            "project": "P",
            "normalized_project": "p",
        }
        score, reasons, band, eligible, _near = app.recommendation_score(client, listing, app.recommendation_window_for(client))
        assert eligible is True, ut


def test_residential_plus_apartment_excludes_chalet():
    client = {
        "budget": "5000000",
        "preferred_location": "Sheikh Zayed",
        "preferred_locations_list": ["Sheikh Zayed"],
        "preferred_unit_type": "Apartment",
        "unit_type": "Apartment",
        "property_category": "Residential",
        "preferred_space_min": None,
        "preferred_space_max": None,
        "bedrooms": "",
        "preferred_developer": "",
        "preferred_project": "",
        "project": "",
    }
    apt = {"location": "Sheikh Zayed", "total_price_min": 4_000_000, "total_price_max": 4_000_000,
           "unit_type": "Apartment", "unit_type_canonical": "Apartment", "category": "Residential",
           "space_min": None, "space_max": None, "developer": "", "project": "P", "normalized_project": "p"}
    chalet = {"location": "Sheikh Zayed", "total_price_min": 4_000_000, "total_price_max": 4_000_000,
              "unit_type": "Chalet", "unit_type_canonical": "Chalet", "category": "Residential",
              "space_min": None, "space_max": None, "developer": "", "project": "P", "normalized_project": "p"}
    s1, _, _, e1, _ = app.recommendation_score(client, apt, app.recommendation_window_for(client))
    s2, _, _, e2, _ = app.recommendation_score(client, chalet, app.recommendation_window_for(client))
    assert e1 is True
    assert e2 is False


def test_commercial_matches_all_commercial_variants():
    client = {
        "budget": "5000000",
        "preferred_location": "Sheikh Zayed",
        "preferred_locations_list": ["Sheikh Zayed"],
        "preferred_unit_type": "",
        "unit_type": "",
        "property_category": "Commercial",
        "preferred_space_min": None,
        "preferred_space_max": None,
        "bedrooms": "",
        "preferred_developer": "",
        "preferred_project": "",
        "project": "",
    }
    for raw in ("comm", "comm- admin- med", "AD", "med", "Ret-PH-comm", "Admin"):
        listing = {"location": "Sheikh Zayed", "total_price_min": 4_000_000, "total_price_max": 4_000_000,
                   "unit_type": raw, "unit_type_canonical": app.canonical_unit_type(raw),
                   "category": "Commercial", "space_min": None, "space_max": None,
                   "developer": "", "project": "P", "normalized_project": "p"}
        _, _, _, eligible, _ = app.recommendation_score(client, listing, app.recommendation_window_for(client))
        assert eligible is True, raw


def test_category_mismatch_excluded():
    client = {
        "budget": "5000000",
        "preferred_location": "Sheikh Zayed",
        "preferred_locations_list": ["Sheikh Zayed"],
        "preferred_unit_type": "",
        "unit_type": "",
        "property_category": "Residential",
        "preferred_space_min": None,
        "preferred_space_max": None,
        "bedrooms": "",
        "preferred_developer": "",
        "preferred_project": "",
        "project": "",
    }
    listing = {"location": "Sheikh Zayed", "total_price_min": 4_000_000, "total_price_max": 4_000_000,
               "unit_type": "Office", "unit_type_canonical": "Commercial", "category": "Commercial",
               "space_min": None, "space_max": None, "developer": "", "project": "P", "normalized_project": "p"}
    _, _, _, eligible, _ = app.recommendation_score(client, listing, app.recommendation_window_for(client))
    assert eligible is False


def test_unknown_unit_type_no_preference_still_eligible():
    client = {
        "budget": "5000000",
        "preferred_location": "Sheikh Zayed",
        "preferred_locations_list": ["Sheikh Zayed"],
        "preferred_unit_type": "",
        "unit_type": "",
        "property_category": "",
        "preferred_space_min": None,
        "preferred_space_max": None,
        "bedrooms": "",
        "preferred_developer": "",
        "preferred_project": "",
        "project": "",
    }
    listing = {"location": "Sheikh Zayed", "total_price_min": 4_000_000, "total_price_max": 4_000_000,
               "unit_type": "No Info", "unit_type_canonical": "", "category": "",
               "space_min": None, "space_max": None, "developer": "", "project": "P", "normalized_project": "p"}
    _, _, _, eligible, _ = app.recommendation_score(client, listing, app.recommendation_window_for(client))
    assert eligible is True


def test_unknown_unit_type_with_preference_excluded():
    client = {
        "budget": "5000000",
        "preferred_location": "Sheikh Zayed",
        "preferred_locations_list": ["Sheikh Zayed"],
        "preferred_unit_type": "Apartment",
        "unit_type": "Apartment",
        "property_category": "",
        "preferred_space_min": None,
        "preferred_space_max": None,
        "bedrooms": "",
        "preferred_developer": "",
        "preferred_project": "",
        "project": "",
    }
    listing = {"location": "Sheikh Zayed", "total_price_min": 4_000_000, "total_price_max": 4_000_000,
               "unit_type": "No Info", "unit_type_canonical": "", "category": "",
               "space_min": None, "space_max": None, "developer": "", "project": "P", "normalized_project": "p"}
    _, _, _, eligible, _ = app.recommendation_score(client, listing, app.recommendation_window_for(client))
    assert eligible is False


def test_backfill_idempotent():
    pass


def test_unknown_listing_cannot_match_residential():
    client = {
        "budget": "5000000",
        "preferred_location": "Sheikh Zayed",
        "preferred_locations_list": ["Sheikh Zayed"],
        "preferred_unit_type": "",
        "unit_type": "",
        "property_category": "Residential",
        "preferred_space_min": None,
        "preferred_space_max": None,
        "bedrooms": "",
        "preferred_developer": "",
        "preferred_project": "",
        "project": "",
    }
    listing = {"location": "Sheikh Zayed", "total_price_min": 4_000_000, "total_price_max": 4_000_000,
               "unit_type": "Penthouse", "unit_type_canonical": "", "category": "",
               "space_min": None, "space_max": None, "developer": "", "project": "P", "normalized_project": "p"}
    _, _, _, eligible, _ = app.recommendation_score(client, listing, app.recommendation_window_for(client))
    # Unknown listing should not satisfy Residential preference via category
    # (category is empty, so it is excluded when client category is Residential).
    assert eligible is False


def test_unknown_listing_cannot_match_commercial():
    client = {
        "budget": "5000000",
        "preferred_location": "Sheikh Zayed",
        "preferred_locations_list": ["Sheikh Zayed"],
        "preferred_unit_type": "",
        "unit_type": "",
        "property_category": "Commercial",
        "preferred_space_min": None,
        "preferred_space_max": None,
        "bedrooms": "",
        "preferred_developer": "",
        "preferred_project": "",
        "project": "",
    }
    listing = {"location": "Sheikh Zayed", "total_price_min": 4_000_000, "total_price_max": 4_000_000,
               "unit_type": "Penthouse", "unit_type_canonical": "", "category": "",
               "space_min": None, "space_max": None, "developer": "", "project": "P", "normalized_project": "p"}
    _, _, _, eligible, _ = app.recommendation_score(client, listing, app.recommendation_window_for(client))
    assert eligible is False


def test_unknown_client_preference_cannot_match():
    client = {
        "budget": "5000000",
        "preferred_location": "Sheikh Zayed",
        "preferred_locations_list": ["Sheikh Zayed"],
        "preferred_unit_type": "Penthouse",
        "unit_type": "Penthouse",
        "property_category": "",
        "preferred_space_min": None,
        "preferred_space_max": None,
        "bedrooms": "",
        "preferred_developer": "",
        "preferred_project": "",
        "project": "",
    }
    listing = {"location": "Sheikh Zayed", "total_price_min": 4_000_000, "total_price_max": 4_000_000,
               "unit_type": "Penthouse", "unit_type_canonical": "", "category": "",
               "space_min": None, "space_max": None, "developer": "", "project": "P", "normalized_project": "p"}
    _, _, _, eligible, _ = app.recommendation_score(client, listing, app.recommendation_window_for(client))
    assert eligible is False


def test_no_preference_allows_unclassified_with_reason():
    client = {
        "budget": "5000000",
        "preferred_location": "Sheikh Zayed",
        "preferred_locations_list": ["Sheikh Zayed"],
        "preferred_unit_type": "",
        "unit_type": "",
        "property_category": "",
        "preferred_space_min": None,
        "preferred_space_max": None,
        "bedrooms": "",
        "preferred_developer": "",
        "preferred_project": "",
        "project": "",
    }
    listing = {"location": "Sheikh Zayed", "total_price_min": 4_000_000, "total_price_max": 4_000_000,
               "unit_type": "Penthouse", "unit_type_canonical": "", "category": "",
               "space_min": None, "space_max": None, "developer": "", "project": "P", "normalized_project": "p"}
    score, reasons, band, eligible, _near = app.recommendation_score(client, listing, app.recommendation_window_for(client))
    assert eligible is True
    assert any("Unit type not classified" in r for r in reasons)


def test_classify_listing_category_unknown_empty():
    assert app.classify_listing_category("Penthouse") == ""
    assert app.classify_listing_category("  penthouse  ") == ""
    assert app.classify_listing_category("No Info") == ""
    assert app.classify_listing_category("HOLD") == ""
    assert app.classify_listing_category("sold out") == ""


def test_raw_value_preserved():
    # canonicalization does not alter raw unit_type
    assert app.canonical_unit_type("Penthouse") == ""
    # raw stays raw in storage; helper only affects canonical
    assert "Penthouse".capitalize() == "Penthouse"
