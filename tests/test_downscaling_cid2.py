from pathlib import Path

import pytest

import rpa_geo
from rpa_geo.crosswalks.downscaling_cid2 import resolve

DOWNSCALING_RAW = (
    Path(__file__).parent.parent.parent
    / "rpa-socioeconomic-downscaling"
    / "data"
    / "raw"
)
IMPORTABLE_XLSX = DOWNSCALING_RAW / "importable19.xlsx"
HTF_HISTORICAL_XLSX = DOWNSCALING_RAW / "htf_historical_data_by_county_all.xlsx"
HTF_PROJECTED_XLSX = DOWNSCALING_RAW / "htf_projected_data_by_county_all.xlsx"

live_data_available = pytest.mark.skipif(
    not (
        IMPORTABLE_XLSX.exists()
        and HTF_HISTORICAL_XLSX.exists()
        and HTF_PROJECTED_XLSX.exists()
    ),
    reason="rpa-socioeconomic-downscaling's raw data isn't present on this checkout (gitignored sibling repo data)",
)


def test_direct_passthrough():
    r = resolve("06059")
    assert r.status == "direct"
    assert r.canonical_geoids == ("06059",)


def test_history_edge():
    r = resolve("46113")
    assert r.status == "history_edge"
    assert r.canonical_geoids == ("46102",)


def test_ct_old_county_allocation():
    r = resolve("09001")
    assert r.status == "ct_allocation"
    assert set(r.canonical_geoids) <= {
        "09110",
        "09120",
        "09130",
        "09140",
        "09150",
        "09160",
        "09170",
        "09180",
        "09190",
    }
    assert r.shares is not None
    assert sum(r.shares) == pytest.approx(1.0, abs=1e-4)


@pytest.mark.parametrize(
    "cid2", ["09001", "09003", "09005", "09007", "09009", "09011", "09013", "09015"]
)
def test_all_old_ct_counties_resolve(cid2):
    r = resolve(cid2)
    assert r.status == "ct_allocation"
    assert len(r.canonical_geoids) >= 1


def test_ak_split_allocation():
    r = resolve("02261")  # Valdez-Cordova
    assert r.status == "ak_split_allocation"
    assert set(r.canonical_geoids) == {"02063", "02066"}


def test_puerto_rico_passes_through_directly():
    r = resolve("72001")
    assert r.status == "direct"
    assert r.canonical_geoids == ("72001",)


def test_guam_resolves_1to1():
    r = resolve("73001")
    assert r.status == "pacific_1to1"
    assert r.canonical_geoids == ("66010",)


def test_american_samoa_flagged_unresolved_not_silently_dropped():
    r = resolve("74001")
    assert r.status == "pacific_unresolved"
    assert len(r.canonical_geoids) == 5
    assert all(g.startswith("600") for g in r.canonical_geoids)


def test_marshall_islands_out_of_scope_not_silently_dropped():
    r = resolve("75001")
    assert r.status == "out_of_scope"
    assert r.canonical_geoids == ()
    assert "marshall" in r.note.lower()


def test_wake_island_out_of_scope_not_silently_dropped():
    r = resolve("76001")
    assert r.status == "out_of_scope"
    assert r.canonical_geoids == ()


def test_inert_ak_remainder_placeholder():
    r = resolve("02999")
    assert r.status == "inert_placeholder"


def test_deep_legacy_ak_code_flagged_for_review_not_guessed():
    r = resolve("02231")
    assert r.status == "unresolved_needs_review"


def test_unknown_code_flagged_for_review():
    r = resolve("00000")
    assert r.status == "unresolved_needs_review"


@live_data_available
def test_every_live_cid2_value_resolves_to_a_known_status():
    import pandas as pd

    imp = pd.read_excel(IMPORTABLE_XLSX, sheet_name="importable", usecols=["cid2"])
    htf_h = pd.read_excel(
        HTF_HISTORICAL_XLSX, sheet_name="htf_data_by_county", usecols=["cid2"]
    )
    htf_p = pd.read_excel(
        HTF_PROJECTED_XLSX,
        sheet_name="htf_projected_data_by_county_al",
        usecols=["cid2"],
    )

    universe = sorted(
        {int(v) for v in imp["cid2"].dropna().unique()}
        | {int(v) for v in htf_h["cid2"].dropna().unique()}
        | {int(v) for v in htf_p["cid2"].dropna().unique()}
    )
    assert (
        len(universe) > 3000
    )  # sanity: this really is the live full universe, not an empty read

    counties = rpa_geo.load_counties()
    unresolved = []
    for v in universe:
        r = resolve(str(v))
        if r.status == "unresolved_needs_review":
            unresolved.append(r.cid2)
        elif r.status in ("direct", "history_edge", "pacific_1to1"):
            assert len(r.canonical_geoids) == 1
            assert r.canonical_geoids[0] in counties
        elif r.status in ("ct_allocation", "ak_split_allocation"):
            assert all(g in counties for g in r.canonical_geoids)
            assert r.shares is not None
            assert sum(r.shares) == pytest.approx(1.0, abs=1e-4)
        elif r.status == "pacific_unresolved":
            assert all(g in counties for g in r.canonical_geoids)
        # out_of_scope / inert_placeholder: no canonical_geoids expected

    # Every genuinely unresolved code must be one we've explicitly flagged and
    # explained (see UNRESOLVED_CID2) -- never a silent surprise.
    from rpa_geo.crosswalks.downscaling_cid2 import UNRESOLVED_CID2

    assert set(unresolved) <= set(UNRESOLVED_CID2)
