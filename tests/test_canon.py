import pytest

import rpa_geo


def test_available_vintages_includes_2025():
    assert "2025" in rpa_geo.available_vintages()


def test_latest_vintage_defaults_to_2025():
    assert rpa_geo.LATEST_VINTAGE == "2025"


def test_load_counties_explicit_vintage_matches_default():
    assert rpa_geo.load_counties(vintage="2025") == rpa_geo.load_counties()


def test_load_counties_unknown_vintage_raises():
    with pytest.raises(ValueError, match="2031"):
        rpa_geo.load_counties(vintage="2031")


def test_nonstandard_county_equivalents_matches_known_cases():
    nse = rpa_geo.nonstandard_county_equivalents()
    # independent cities (mechanically derived from lsad) + hand-curated
    # consolidated city-county governments and DC
    for expected in ("11001", "08031", "08014", "32510", "29510", "51510"):
        assert expected in nse, f"{expected} should be a nonstandard county-equivalent"
    # an ordinary county missing from some *other* repo's reference table
    # for an unrelated reason (rpa-landuse-2030 issue #87) is not this shape
    assert "51013" not in nse  # Arlington County, VA -- an ordinary county


def test_nonstandard_county_equivalents_are_all_real_canonical_geoids():
    counties = rpa_geo.load_counties()
    for geoid in rpa_geo.nonstandard_county_equivalents():
        assert geoid in counties


def test_counties_full_census_universe_scope():
    counties = rpa_geo.load_counties()
    assert len(counties) == 3235

    by_stusps: dict[str, int] = {}
    for c in counties.values():
        by_stusps[c.stusps] = by_stusps.get(c.stusps, 0) + 1

    assert by_stusps["GU"] == 1
    assert by_stusps["AS"] == 5
    assert by_stusps["MP"] == 4
    assert by_stusps["VI"] == 3
    assert by_stusps["PR"] == 78
    assert by_stusps["CT"] == 9  # new planning regions, not the old 8 counties


def test_marshall_islands_and_wake_island_not_in_canonical_table():
    counties = rpa_geo.load_counties()
    assert "75001" not in counties
    assert "76001" not in counties


def test_out_of_scope_registry_flags_marshall_and_wake():
    out_of_scope = rpa_geo.load_out_of_scope()
    assert "75001" in out_of_scope
    assert "76001" in out_of_scope
    assert "marshall" in out_of_scope["75001"].reason.lower()
    assert "wake" in out_of_scope["76001"].label.lower()


def test_every_history_edge_target_is_a_real_canonical_county():
    counties = rpa_geo.load_counties()
    edges = rpa_geo.load_history_edges()
    assert len(edges) == 30
    for edge in edges.values():
        assert edge.canonical_geoid in counties, (
            f"{edge.legacy_geoid} -> {edge.canonical_geoid} is not canonical"
        )
        # the legacy code itself must NOT be a current canonical GEOID (it's retired/repo-internal)
        assert edge.legacy_geoid not in counties, (
            f"{edge.legacy_geoid} is unexpectedly still canonical"
        )


def test_canonical_geoid_direct_passthrough():
    assert rpa_geo.canonical_geoid("06059") == "06059"  # Orange County, CA


def test_canonical_geoid_resolves_known_history_edges():
    assert rpa_geo.canonical_geoid("46113") == "46102"  # Shannon -> Oglala Lakota, SD
    assert rpa_geo.canonical_geoid("02270") == "02158"  # Wade Hampton -> Kusilvak, AK


def test_canonical_geoid_unknown_returns_none():
    assert rpa_geo.canonical_geoid("99999") is None
