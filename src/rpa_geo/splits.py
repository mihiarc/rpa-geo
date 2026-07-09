"""Historical one-to-many / many-to-many GEOID splits.

Some predecessor GEOIDs don't map 1:1 to a canonical GEOID -- they were
divided among several current counties/equivalents, so there is no single
"the" canonical answer, only an allocation. See ``data/historical_splits.csv``
and README.md for how each case was built (CT's 2022 planning-region switch,
and three Alaska Census Area splits/retirements: Wrangell-Petersburg 2008,
Skagway-Hoonah-Angoon 2007, Valdez-Cordova 2019).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from functools import lru_cache

from rpa_geo.canon import data_path

OLD_CT_COUNTY_FIPS = frozenset(
    {"09001", "09003", "09005", "09007", "09009", "09011", "09013", "09015"}
)
NEW_CT_REGION_FIPS = frozenset(
    {"09110", "09120", "09130", "09140", "09150", "09160", "09170", "09180", "09190"}
)


@dataclass(frozen=True, slots=True)
class Split:
    predecessor_geoid: str
    successor_geoid: str
    weight_basis: str
    share_of_predecessor: float
    share_of_new_region: float
    case: str
    note: str


@lru_cache(maxsize=1)
def historical_splits() -> tuple[Split, ...]:
    """Every (predecessor, successor) pair with a nonzero allocated share."""
    rows = []
    text = data_path("historical_splits.csv").read_text(encoding="utf-8")
    for row in csv.DictReader(io.StringIO(text)):
        rows.append(
            Split(
                predecessor_geoid=row["predecessor_geoid"],
                successor_geoid=row["successor_geoid"],
                weight_basis=row["weight_basis"],
                share_of_predecessor=float(row["share_of_predecessor"]),
                share_of_new_region=float(row["share_of_new_region"]),
                case=row["case"],
                note=row["note"],
            )
        )
    return tuple(rows)


def resolve_predecessor(predecessor_geoid: str) -> tuple[Split, ...]:
    """All successor allocations for one predecessor GEOID, largest share first.

    Returns an empty tuple if ``predecessor_geoid`` isn't a known split
    predecessor -- callers should treat that as "not a split case", not as
    an error, since most GEOIDs never split.
    """
    matches = [
        row for row in historical_splits() if row.predecessor_geoid == predecessor_geoid
    ]
    return tuple(sorted(matches, key=lambda r: r.share_of_predecessor, reverse=True))


def resolve_ct_old_county(old_county_fips: str) -> tuple[Split, ...]:
    """Convenience wrapper: all new-region allocations for one old CT county."""
    if old_county_fips not in OLD_CT_COUNTY_FIPS:
        raise ValueError(
            f"{old_county_fips!r} is not one of CT's old 8 counties (09001-09015)"
        )
    return resolve_predecessor(old_county_fips)
