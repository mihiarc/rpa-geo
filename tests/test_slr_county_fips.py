import rpa_geo
from crosswalks.slr_county_fips import resolve


def test_direct_passthrough():
    r = resolve("06059")
    assert r.canonical_geoid == "06059"


def test_ct_new_region_passes_through():
    r = resolve("09190")  # rpa-slr is already on the new CT planning-region GEOIDs
    assert r.canonical_geoid == "09190"


def test_unknown_geoid_flagged_not_silently_passed():
    r = resolve("99999")
    assert r.canonical_geoid is None


def test_every_canonical_geoid_round_trips():
    counties = rpa_geo.load_counties()
    for geoid in counties:
        r = resolve(geoid)
        assert r.canonical_geoid == geoid
