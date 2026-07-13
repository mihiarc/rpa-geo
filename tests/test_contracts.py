from types import SimpleNamespace
from typing import get_args

import pandera.errors as pandera_errors
import pytest

from rpa_geo import contracts
from rpa_geo.crosswalks import downscaling_cid2, landuse2030_fips, slr_county_fips


@pytest.mark.parametrize(
    "status_literal",
    [downscaling_cid2.Status, landuse2030_fips.Status, slr_county_fips.Status],
)
def test_every_crosswalk_status_has_a_registered_category(status_literal):
    for status in get_args(status_literal):
        assert status in contracts.STATUS_CATEGORY, (
            f"{status!r} has no Category -- add it to contracts.STATUS_CATEGORY"
        )


def test_category_raises_on_unregistered_status():
    with pytest.raises(KeyError):
        contracts.category("some_future_status_nobody_registered_yet")


@pytest.mark.parametrize(
    ("status", "expected_category"),
    [
        ("direct", "direct"),
        ("history_edge", "history_edge"),
        ("ct_allocation", "split_allocation"),
        ("ak_split_allocation", "split_allocation"),
        ("pacific_1to1", "direct"),
        ("pacific_unresolved", "territory_fanout"),
        ("out_of_scope", "out_of_scope"),
        ("inert_placeholder", "inert_placeholder"),
        ("unresolved_needs_review", "unresolved_needs_review"),
        ("ct_duplicate_direct", "unresolved_needs_review"),
        ("out_of_scope_by_design", "out_of_scope"),
        ("out_of_scope_but_present", "unresolved_needs_review"),
        ("unresolved", "unresolved_needs_review"),
    ],
)
def test_category_mapping(status, expected_category):
    assert contracts.category(status) == expected_category


def test_resolved_categories_excludes_live_gaps():
    # territory_fanout and unresolved_needs_review represent genuine open
    # gaps (no weights, or a real unknown) -- they must never be silently
    # treated as "clean" by the default allow-set.
    assert "territory_fanout" not in contracts.RESOLVED_CATEGORIES
    assert "unresolved_needs_review" not in contracts.RESOLVED_CATEGORIES


def test_validate_universe_passes_on_clean_universe():
    downscaling_cid2.validate_universe(["06059", "09001", "02261"])


def test_validate_universe_raises_on_known_unresolved_code():
    # An unknown code (not canonical, not an edge/split/special case) resolves
    # to unresolved_needs_review via the catch-all, and validate_universe fails.
    with pytest.raises(pandera_errors.SchemaErrors) as excinfo:
        downscaling_cid2.validate_universe(["00000"])
    failures = excinfo.value.failure_cases
    assert "00000" in set(failures["index"])
    assert "unresolved_needs_review" in set(failures["failure_case"])


def _resolves_to(status):
    """A minimal resolve() stand-in returning a fixed status, for exercising
    the contract machinery independent of any live crosswalk value."""

    def _resolve(_key):
        return SimpleNamespace(status=status)

    return _resolve


def test_validate_universe_raises_on_territory_fanout():
    # No live cid2 resolves to territory_fanout anymore (American Samoa 74001
    # was settled as a drop on 2026-07-13), so drive the machinery directly.
    with pytest.raises(pandera_errors.SchemaErrors) as excinfo:
        contracts.validate_universe(["x"], _resolves_to("pacific_unresolved"))
    failures = excinfo.value.failure_cases
    assert "territory_fanout" in set(failures["failure_case"])


def test_validate_universe_caller_can_widen_allow_set():
    # A caller who's consciously decided to tolerate a live gap can opt in
    # explicitly -- the default just doesn't make that choice for them.
    contracts.validate_universe(
        ["x"],
        _resolves_to("pacific_unresolved"),
        allow=contracts.RESOLVED_CATEGORIES | {"territory_fanout"},
    )
