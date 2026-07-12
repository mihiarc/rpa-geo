"""Crosswalk from rpa-slr / rpa-slr-landuse's ``county_fips`` to rpa-geo's canonical GEOID.

Both repos key on ``county_fips`` (string) from Census TIGER/Line **2024**
(``rpa-slr/data/input/shapefile_county_census/tl_2024_us_county.shp``;
rpa-slr-landuse reads the same file directly, see its
``config.py::COUNTY_BOUNDARY_TL2024``). Both are already on the current CT
planning-region GEOIDs (09110-09190), not the retired county FIPS.

Verified by diffing the full national county attribute tables for the 2024
and 2025 cartographic boundary files (``cb_2024_us_county_500k`` vs
``cb_2025_us_county_500k`` -- the generalized files share the identical
GEOID universe as the full-resolution TIGER files for the same vintage
year): **zero GEOID changes**. Same 3,235 GEOIDs, same names; the only
differences are sub-square-meter ALAND rounding noise from hydrography
updates, not real boundary changes. So this crosswalk is a pure identity
mapping -- included as a real module (not skipped) so the "which vintage do
I use" question has one documented, tested answer instead of being
silently assumed.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

import rpa_geo
from rpa_geo import contracts

Status = Literal[
    "direct",  # county_fips IS the canonical GEOID already
    "unresolved",  # not a canonical GEOID -- unexpected, since 2024->2025 changed nothing
]


@dataclass(frozen=True, slots=True)
class Resolution:
    county_fips: str
    status: Status
    canonical_geoid: str | None
    note: str


def resolve(county_fips: str) -> Resolution:
    county_fips = str(county_fips).strip().zfill(5)
    counties = rpa_geo.load_counties()
    if county_fips in counties:
        return Resolution(
            county_fips,
            "direct",
            county_fips,
            "TIGER/Line 2024 and 2025 share an identical GEOID universe (verified by full diff) -- direct passthrough.",
        )
    return Resolution(
        county_fips,
        "unresolved",
        None,
        "Not a canonical 2025 GEOID. Since 2024->2025 introduced zero real changes, this is unexpected for a genuine tl_2024 county_fips value -- check for a data entry error rather than assuming a missing recode.",
    )


def validate_universe(
    county_fips_values: Iterable[str],
    *,
    allow: frozenset[contracts.Category] = contracts.RESOLVED_CATEGORIES,
) -> None:
    """Raise if any value resolves outside ``allow`` -- see rpa_geo.contracts."""
    contracts.validate_universe(county_fips_values, resolve, allow=allow)
