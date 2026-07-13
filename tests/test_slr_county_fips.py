import pandera.errors as pandera_errors
import pytest

import rpa_geo
from rpa_geo.crosswalks.slr_county_fips import resolve, validate_universe


def test_direct_passthrough():
    r = resolve("06059")
    assert r.status == "direct"
    assert r.canonical_geoid == "06059"


def test_ct_new_region_passes_through():
    r = resolve("09190")  # rpa-slr is already on the new CT planning-region GEOIDs
    assert r.status == "direct"
    assert r.canonical_geoid == "09190"


def test_unknown_geoid_flagged_not_silently_passed():
    r = resolve("99999")
    assert r.status == "unresolved"
    assert r.canonical_geoid is None


def test_validate_universe_passes_on_clean_universe():
    validate_universe(["06059", "09190"])


def test_validate_universe_raises_on_unresolved():
    with pytest.raises(pandera_errors.SchemaErrors) as excinfo:
        validate_universe(["99999"])
    assert "99999" in set(excinfo.value.failure_cases["index"])


def test_every_canonical_geoid_round_trips():
    counties = rpa_geo.load_counties()
    for geoid in counties:
        r = resolve(geoid)
        assert r.canonical_geoid == geoid
