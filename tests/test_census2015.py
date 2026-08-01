"""Tests for the canonical 2025 <-> 2015-scheme link.

The AK/CT fixtures below are transcribed directly from the owner's two
source files (Alaska_locations_final.xlsx and
ct_cou_to_cousub_crosswalk_final_choices.xlsx, J. Prestemon, 2026-07-16) --
they are the contract this module must keep matching, independent of how
the CSVs or shared split/edge tables evolve.
"""

from pathlib import Path

import pytest

import rpa_geo
from rpa_geo import contracts
from rpa_geo.crosswalks.census2015 import (
    MEMBERSHIP_2015_UNKNOWN,
    ak_locations,
    from_2015,
    resolve,
    validate_universe,
)

IMPORTABLE_XLSX = (
    Path(__file__).parent.parent.parent
    / "rpa-socioeconomic-downscaling"
    / "data"
    / "raw"
    / "importable19.xlsx"
)

live_data_available = pytest.mark.skipif(
    not IMPORTABLE_XLSX.exists(),
    reason="rpa-socioeconomic-downscaling's raw data isn't present on this checkout (gitignored sibling repo data)",
)

# Every 2015 AK location -> the current GEOIDs that feed it, verbatim from
# Alaska_locations_final.xlsx. Exactly partitions the 30 current AK
# county-equivalents into the owner's 24 locations.
AK_MEMBERSHIP = {
    "02013": {"02013"},
    "02016": {"02016"},
    "02020": {"02020"},
    "02050": {"02050"},
    "02060": {"02060"},
    "02070": {"02070", "02164"},  # Dillingham + Lake and Peninsula
    "02090": {"02090"},
    "02100": {"02100"},
    "02110": {"02110"},
    "02122": {"02122"},
    "02130": {"02130"},
    "02150": {"02150"},
    "02170": {"02170"},
    "02180": {"02180"},
    "02185": {"02185"},
    "02188": {"02188"},
    "02201": {"02198"},  # Prince of Wales-Hyder, scheme keeps retired code
    "02220": {"02220"},
    "02231": {"02230", "02282", "02105"},  # Skagway + Yakutat + Hoonah-Angoon
    "02240": {"02240"},
    "02261": {"02063", "02066"},  # Chugach + Copper River
    "02270": {"02158"},  # Kusilvak, scheme keeps Wade Hampton code
    "02280": {"02275", "02195"},  # Wrangell + Petersburg
    "02290": {"02290", "02068"},  # Yukon-Koyukuk + Denali
}

# Owner's final 1:1 CT choices, verbatim from the
# Final_Assignment_for_Urban_Rent sheet (old county -> assigned region).
CT_ASSIGNMENT = {
    "09001": "09120",  # Fairfield -> Greater Bridgeport (NOT the largest share)
    "09003": "09110",  # Hartford -> Capitol
    "09005": "09160",  # Litchfield -> Northwest Hills
    "09007": "09130",  # Middlesex -> Lower CT River Valley
    "09009": "09140",  # New Haven -> Naugatuck Valley (NOT the largest share)
    "09011": "09180",  # New London -> Southeastern CT
    "09013": "09110",  # Tolland -> Capitol (09110 is read twice)
    "09015": "09150",  # Windham -> Northeastern CT
}
CT_UNASSIGNED = {"09170", "09190"}  # South Central + Western: deliberately unread


def test_ak_membership_partitions_all_current_ak_counties():
    counties = rpa_geo.load_counties()
    current_ak = {g for g in counties if g.startswith("02")}
    covered = set().union(*AK_MEMBERSHIP.values())
    assert covered == current_ak
    # and no current GEOID feeds two locations
    assert sum(len(v) for v in AK_MEMBERSHIP.values()) == len(current_ak) == 30


@pytest.mark.parametrize(("location", "members"), sorted(AK_MEMBERSHIP.items()))
def test_ak_resolve_matches_owner_file(location, members):
    for member in members:
        r = resolve(member)
        assert r.geoids_2015 == (location,), (member, r)
        assert r.status in ("identity", "renamed", "ak_aggregate_member")


@pytest.mark.parametrize(("location", "members"), sorted(AK_MEMBERSHIP.items()))
def test_ak_from_2015_round_trip(location, members):
    loc = from_2015(location)
    assert set(loc.geoids_2025) == members
    if len(members) > 1:
        assert loc.kind == "ak_aggregate"


def test_ak_aggregates_agree_with_historical_splits():
    # The link CSV and historical_splits.csv encode the same owner facts in
    # two shapes -- this pins them together so they can't drift apart.
    for pred in ("02231", "02261", "02280", "02070", "02290"):
        split_successors = {
            s.successor_geoid for s in rpa_geo.resolve_predecessor(pred)
        }
        assert split_successors == AK_MEMBERSHIP[pred], pred


def test_ak_locations_attributes():
    locs = ak_locations()
    assert set(locs) == set(AK_MEMBERSHIP)
    # coastal flags verbatim from the owner's file: exactly 4 non-coastal
    non_coastal = {k for k, v in locs.items() if not v.coastal}
    assert non_coastal == {"02090", "02231", "02240", "02290"}
    # Aleutians West's interior point legitimately crosses the antimeridian
    assert locs["02016"].intptlon > 0


@pytest.mark.parametrize(("old_county", "region"), sorted(CT_ASSIGNMENT.items()))
def test_ct_owner_assignment(old_county, region):
    assert old_county in resolve(region).geoids_2015
    assert from_2015(old_county).geoids_2025 == (region,)
    assert from_2015(old_county).kind == "ct_assigned_region"


def test_ct_capitol_region_is_read_twice():
    r = resolve("09110")
    assert r.status == "ct_owner_assignment"
    assert set(r.geoids_2015) == {"09003", "09013"}


def test_ct_unassigned_regions_are_flagged_not_dropped():
    for region in CT_UNASSIGNED:
        r = resolve(region)
        assert r.status == "ct_owner_unassigned"
        assert r.geoids_2015 == ()
        assert contracts.category(r.status) == "inert_placeholder"


def test_renamed_counties_keep_2015_codes():
    assert resolve("46102").geoids_2015 == ("46113",)  # Oglala Lakota -> Shannon
    assert resolve("02158").geoids_2015 == ("02270",)  # Kusilvak -> Wade Hampton
    assert resolve("02198").geoids_2015 == ("02201",)  # PoW-Hyder -> PoW-OK
    # Dade -> Miami-Dade (1997) predates the scheme: 12086 stays itself.
    assert resolve("12086").status == "identity"


def test_va_combo_principals_resolve_to_their_combo():
    r = resolve("51003")  # Albemarle -> Albemarle + Charlottesville combo
    assert r.status == "combo_member"
    assert r.geoids_2015 == ("51901",)
    assert resolve("15009").geoids_2015 == ("15901",)  # Maui
    assert resolve("55078").geoids_2015 == ("55901",)  # Menominee


def test_confirmed_combo_minor_members_resolve_too():
    # Owner-confirmed 2026-07-30: 15901 = Maui + Kalawao, 55901 = Shawano +
    # Menominee. Kalawao and Shawano were membership_2015_unknown before that.
    for member, combo in (("15005", "15901"), ("55115", "55901")):
        r = resolve(member)
        assert r.status == "combo_member"
        assert r.geoids_2015 == (combo,)
    assert "15005" not in MEMBERSHIP_2015_UNKNOWN
    assert "55115" not in MEMBERSHIP_2015_UNKNOWN


def test_confirmed_combos_from_2015_return_complete_membership():
    for combo, members in (
        ("15901", {"15009", "15005"}),
        ("55901", {"55115", "55078"}),
    ):
        loc = from_2015(combo)
        assert loc.kind == "combo"
        assert set(loc.geoids_2025) == members
        assert "complete" in loc.note.lower()


def test_membership_unknown_codes_are_flagged_not_guessed():
    assert "51540" in MEMBERSHIP_2015_UNKNOWN  # Charlottesville
    for geoid in MEMBERSHIP_2015_UNKNOWN:
        r = resolve(geoid)
        assert r.status == "membership_2015_unknown"
        assert r.geoids_2015 == ()
        assert contracts.category(r.status) == "unresolved_needs_review"


def test_combo_from_2015_returns_confirmed_members_only():
    loc = from_2015("51901")
    assert loc.kind == "combo"
    assert loc.geoids_2025 == ("51003",)  # Charlottesville NOT silently included
    assert "gap" in loc.note.lower()


def test_territories():
    assert resolve("60010").status == "owner_excluded"  # American Samoa
    assert resolve("66010").geoids_2015 == ("73001",)  # Guam placeholder
    assert resolve("69100").status == "territory_unmodeled"  # N. Marianas
    assert resolve("72001").status == "identity"  # PR is in the scheme
    assert resolve("78010").status == "identity"  # VI is in the scheme


def test_non_canonical_input_is_flagged():
    r = resolve("02231")  # a 2015-scheme code, not a current GEOID
    assert r.status == "not_canonical_2025"
    assert "downscaling_cid2" in r.note


def test_legacy_panel_only_codes_are_not_2015_locations():
    # 02232 / 02999 exist in the live panel but are NOT among the owner's 24
    # final locations -- from_2015 must say so rather than invent an answer.
    for code in ("02232", "02999"):
        assert from_2015(code).kind == "unknown_2015_code"


def test_every_canonical_geoid_resolves_to_a_registered_status():
    for geoid in rpa_geo.load_counties():
        r = resolve(geoid)
        contracts.category(r.status)  # raises KeyError if unregistered
        if r.status in ("identity", "renamed", "ak_aggregate_member", "combo_member"):
            assert len(r.geoids_2015) == 1


def test_validate_universe_raises_only_on_the_documented_gaps():
    import pandera.errors

    clean = [
        g
        for g in rpa_geo.load_counties()
        if g not in MEMBERSHIP_2015_UNKNOWN and not g.startswith("69")
    ]
    validate_universe(clean)  # must not raise
    with pytest.raises(pandera.errors.SchemaErrors):
        validate_universe(["51540"])  # Charlottesville: a real, documented gap


@live_data_available
def test_link_targets_exist_in_live_cid2_universe():
    import pandas as pd

    imp = pd.read_excel(IMPORTABLE_XLSX, sheet_name="importable", usecols=["cid2"])
    cid2 = {str(int(v)).zfill(5) for v in imp["cid2"].dropna().unique()}

    targets = set()
    for geoid in rpa_geo.load_counties():
        targets.update(resolve(geoid).geoids_2015)
    # 73001 (Guam) only appears in the HTF inputs, not the econometric panel.
    assert targets - cid2 == {"73001"}

    # And the reverse: every live cid2 code is either a link target or one of
    # the documented panel-only codes (never a silent mystery). The six AK
    # member counties here have standalone panel series even though the
    # owner's final file carries their areas inside the 02070/02231/02280
    # aggregates -- and the panel's own dropthis flags are inconsistent about
    # it (02105/02195 dropped, 02164/02230/02275/02282 kept). That
    # discrepancy is the downscaling repo's to settle, not this package's;
    # it's pinned here so a change on their side surfaces as a test diff.
    panel_only = {
        "02232",  # Skagway-Hoonah-Angoon: superseded interim geography
        "02999",  # REMAINDER OF ALASKA: inert placeholder
        "02105",  # Hoonah-Angoon      -- member of 02231 (dropthis=1)
        "02164",  # Lake and Peninsula -- member of 02070 (dropthis=0!)
        "02195",  # Petersburg         -- member of 02280 (dropthis=1)
        "02230",  # Skagway            -- member of 02231 (dropthis=0!)
        "02275",  # Wrangell           -- member of 02280 (dropthis=0!)
        "02282",  # Yakutat            -- member of 02231 (dropthis=0!)
    }
    assert cid2 - targets == panel_only
