import pytest

import rpa_geo
from rpa_geo.splits import NEW_CT_REGION_FIPS, OLD_CT_COUNTY_FIPS


def test_ct_old_county_shares_sum_to_one():
    for old_fips in OLD_CT_COUNTY_FIPS:
        splits = rpa_geo.resolve_ct_old_county(old_fips)
        assert splits, f"no allocation found for old CT county {old_fips}"
        total_share = sum(s.share_of_predecessor for s in splits)
        assert total_share == pytest.approx(1.0, abs=1e-4)
        for s in splits:
            assert s.successor_geoid in NEW_CT_REGION_FIPS


def test_ct_new_region_shares_sum_to_one():
    counties = rpa_geo.load_counties()
    for new_fips in NEW_CT_REGION_FIPS:
        assert new_fips in counties
        matches = [
            s for s in rpa_geo.historical_splits() if s.successor_geoid == new_fips
        ]
        total_share = sum(s.share_of_new_region for s in matches)
        assert total_share == pytest.approx(1.0, abs=1e-4)


def test_ct_old_county_population_shares_sum_to_one():
    for old_fips in OLD_CT_COUNTY_FIPS:
        splits = rpa_geo.resolve_ct_old_county(old_fips)
        assert splits, f"no allocation found for old CT county {old_fips}"
        for s in splits:
            assert s.population_weight_basis == "town_population_2020"
            assert s.population_share_of_predecessor is not None
        total_share = sum(s.population_share_of_predecessor for s in splits)
        assert total_share == pytest.approx(1.0, abs=1e-4)


def test_ct_new_region_population_shares_sum_to_one():
    for new_fips in NEW_CT_REGION_FIPS:
        matches = [
            s for s in rpa_geo.historical_splits() if s.successor_geoid == new_fips
        ]
        for s in matches:
            assert s.population_share_of_new_region is not None
        total_share = sum(s.population_share_of_new_region for s in matches)
        assert total_share == pytest.approx(1.0, abs=1e-4)


def test_ak_splits_have_no_population_weights():
    ak_predecessors = {"02280", "02232", "02261", "02231", "02070", "02290"}
    for pred in ak_predecessors:
        for s in rpa_geo.resolve_predecessor(pred):
            assert s.population_weight_basis is None
            assert s.population_share_of_predecessor is None
            assert s.population_share_of_new_region is None


def test_ct_old_county_rejects_non_ct_input():
    with pytest.raises(ValueError):
        rpa_geo.resolve_ct_old_county("06059")


def test_ak_splits_shares_sum_to_one():
    counties = rpa_geo.load_counties()
    ak_predecessors = {"02280", "02232", "02261", "02231", "02070", "02290"}
    for pred in ak_predecessors:
        splits = rpa_geo.resolve_predecessor(pred)
        assert splits, f"no allocation found for AK predecessor {pred}"
        total_share = sum(s.share_of_predecessor for s in splits)
        assert total_share == pytest.approx(1.0, abs=1e-4)
        for s in splits:
            assert s.successor_geoid in counties


def test_resolve_predecessor_unknown_returns_empty():
    assert rpa_geo.resolve_predecessor("06059") == ()
