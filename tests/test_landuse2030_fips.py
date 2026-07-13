from pathlib import Path

import pandera.errors as pandera_errors
import pytest

import rpa_geo
from rpa_geo.crosswalks.landuse2030_fips import (
    CT_DUPLICATE_NEW_REGIONS,
    KNOWN_MISSING_CONUS_GEOIDS,
    UNEXPECTED_NON_CONUS_IN_GEOREF,
    resolve,
    validate_universe,
)
from rpa_geo.splits import NEW_CT_REGION_FIPS

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


def test_ct_new_region_resolves_direct_since_dedup_fix():
    # Previously flagged ct_duplicate_direct; fixed upstream (rpa-landuse-2030
    # PR #86 / issue #80), so 09130 is now just a normal canonical GEOID.
    r = resolve("09130")
    assert r.status == "direct"


def test_non_conus_out_of_scope_by_design():
    r = resolve("02013")  # a normal AK county, not one of the anomalous rows
    assert r.status == "out_of_scope_by_design"


def test_ct_croix_now_out_of_scope_by_design_since_leak_fix():
    # Previously flagged out_of_scope_but_present; fixed upstream
    # (rpa-landuse-2030 PR #86 / issue #81), so St. Croix, VI now correctly
    # falls out via NON_CONUS_STATEFP alone.
    r = resolve("78010")
    assert r.status == "out_of_scope_by_design"


@pytest.mark.parametrize(
    ("attr_name", "fips", "expected_status"),
    [
        ("CT_DUPLICATE_NEW_REGIONS", "09130", "ct_duplicate_direct"),
        ("UNEXPECTED_NON_CONUS_IN_GEOREF", "78010", "out_of_scope_but_present"),
    ],
)
def test_anomaly_status_still_fires_if_reintroduced(
    monkeypatch, attr_name, fips, expected_status
):
    # Both frozensets are empty now that their anomalies are fixed
    # upstream, but resolve()'s corresponding branch must still catch a
    # future regression rather than silently missing one.
    monkeypatch.setattr(
        f"rpa_geo.crosswalks.landuse2030_fips.{attr_name}", frozenset({fips})
    )
    r = resolve(fips)
    assert r.status == expected_status


def test_validate_universe_passes_on_clean_universe():
    validate_universe(["06059", "09001", "12086"])


def test_validate_universe_raises_on_anomaly(monkeypatch):
    monkeypatch.setattr(
        "rpa_geo.crosswalks.landuse2030_fips.UNEXPECTED_NON_CONUS_IN_GEOREF",
        frozenset({"78010"}),
    )
    with pytest.raises(pandera_errors.SchemaErrors) as excinfo:
        validate_universe(["78010"])
    # failure_case reports the resolved *category*, not the raw status --
    # out_of_scope_but_present maps to unresolved_needs_review (see contracts.py)
    assert "unresolved_needs_review" in set(excinfo.value.failure_cases["failure_case"])


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

    # A different anomaly shape: canonical CONUS+DC GEOIDs missing from
    # georef.csv entirely (see KNOWN_MISSING_CONUS_GEOIDS). CT's new 9
    # planning regions are excluded first -- this repo keeps CT's old 8
    # counties by design, that's not a gap.
    conus_geoids = {g for g, c in counties.items() if c.is_conus}
    missing = conus_geoids - set(universe) - NEW_CT_REGION_FIPS
    assert missing == KNOWN_MISSING_CONUS_GEOIDS
