from pathlib import Path

import pytest

import rpa_geo
from crosswalks.landuse2030_fips import (
    CT_DUPLICATE_NEW_REGIONS,
    UNEXPECTED_NON_CONUS_IN_GEOREF,
    resolve,
)

GEOREF_CSV = (
    Path(__file__).parent.parent.parent
    / "rpa-landuse-2030"
    / "data"
    / "processed"
    / "georef.csv"
)
live_data_available = pytest.mark.skipif(
    not GEOREF_CSV.exists(),
    reason="rpa-landuse-2030's processed georef.csv isn't present on this checkout",
)


def test_direct_passthrough():
    r = resolve("06059")
    assert r.status == "direct"
    assert r.canonical_geoids == ("06059",)


def test_dade_history_edge():
    r = resolve("12025")
    assert r.status == "history_edge"
    assert r.canonical_geoids == ("12086",)


def test_ct_old_county_allocation():
    r = resolve("09001")
    assert r.status == "ct_allocation"
    assert r.shares is not None
    assert sum(r.shares) == pytest.approx(1.0, abs=1e-4)


def test_ct_duplicate_new_region_flagged():
    r = resolve("09130")
    assert r.status == "ct_duplicate_direct"


def test_non_conus_out_of_scope_by_design():
    r = resolve("02013")  # a normal AK county, not one of the anomalous rows
    assert r.status == "out_of_scope_by_design"


def test_unexpected_non_conus_flagged_not_silently_included_or_dropped():
    r = resolve(
        "78010"
    )  # St. Croix, VI -- observed in georef.csv despite CONUS+DC design
    assert r.status == "out_of_scope_but_present"
    assert r.fips in UNEXPECTED_NON_CONUS_IN_GEOREF


@live_data_available
def test_every_live_fips_value_resolves_to_a_known_status():
    import csv

    with GEOREF_CSV.open() as f:
        universe = sorted({row["fips"].zfill(5) for row in csv.DictReader(f)})
    assert len(universe) > 3000

    counties = rpa_geo.load_counties()
    for fips in universe:
        r = resolve(fips)
        assert r.status != "unresolved", f"{fips} did not resolve to any known status"
        if r.status in ("direct", "ct_duplicate_direct", "history_edge"):
            assert r.canonical_geoids[0] in counties
        elif r.status == "ct_allocation":
            assert all(g in counties for g in r.canonical_geoids)
            assert sum(r.shares) == pytest.approx(1.0, abs=1e-4)

    # the anomalies found this pass are exactly the ones already documented --
    # if this ever grows, that's a new finding, not a silent expansion
    ct_dupes_seen = {f for f in universe if f in CT_DUPLICATE_NEW_REGIONS}
    assert ct_dupes_seen == CT_DUPLICATE_NEW_REGIONS
    non_conus_seen = {
        f for f in universe if resolve(f).status == "out_of_scope_but_present"
    }
    assert non_conus_seen == UNEXPECTED_NON_CONUS_IN_GEOREF
