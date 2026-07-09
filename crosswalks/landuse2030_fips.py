"""Crosswalk from rpa-landuse-2030's ``fips`` to rpa-geo's canonical GEOID.

``fips`` is that repo's canonical column name (zero-padded 5-char string;
``county_fips``/``GEOID`` from any source are normalized to it --
``src/landuse_rpa_2030/common/columns.py``). The intended geometry source is
Census **CB-2021** 500k (``src/landuse_rpa_2030/geo.py``), filtered to
CONUS+DC via ``NON_CONUS_STATEFP`` by design.

Verified by diffing the repo's own local
``data/shapefiles/cb_2021_us_county_500k.shp`` against rpa-geo's canonical
2025 table: the **only** difference nationwide is Connecticut's 2022
old-8-county -> new-9-planning-region switch (already covered by
``rpa_geo.splits``). Every other CB-2021 GEOID equals its canonical 2025
GEOID directly.

Validating against the repo's *live* reference table
(``data/processed/georef.csv``, 3,104 distinct fips) surfaced two anomalies
neither the repo's own docs nor rpa-geo's design anticipated -- see
``KNOWN_ANOMALIES`` and the module docstring notes below. Both are flagged
explicitly, not silently resolved, and were reported upstream (see
mihiarc/rpa-landuse-2030 issue tracker).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import rpa_geo
from rpa_geo.splits import OLD_CT_COUNTY_FIPS

Status = Literal[
    "direct",  # fips IS the canonical GEOID already, in CONUS+DC scope
    "history_edge",  # 1:1 legacy code (e.g. Dade -> Miami-Dade), resolved via rpa_geo.history_edges
    "ct_allocation",  # one of CT's old 8 counties -> new 9 planning regions
    "ct_duplicate_direct",  # ANOMALY: one of CT's new regions is present directly IN ADDITION to its old-county predecessors -- risk of double counting if both are summed
    "out_of_scope_by_design",  # non-CONUS per NON_CONUS_STATEFP -- correctly excluded, matches design
    "out_of_scope_but_present",  # ANOMALY: non-CONUS per NON_CONUS_STATEFP, but appears in georef.csv anyway
    "unresolved",
]

# The 2 new CT planning-region GEOIDs observed directly in georef.csv
# ALONGSIDE all 8 old CT counties (Lower Connecticut River Valley 09130,
# Southeastern Connecticut 09180). Middlesex (09007) allocates almost
# entirely into 09130, and New London (09011) + part of Windham (09015)
# allocate into 09180 -- so georef.csv currently represents part of
# Connecticut TWICE: once via the old counties, once via these 2 new
# regions directly. Any code that sums every row in georef.csv without
# deduplicating CT will double-count population/rent data for this area.
CT_DUPLICATE_NEW_REGIONS = frozenset({"09130", "09180"})

# Non-CONUS GEOIDs observed directly in georef.csv despite NON_CONUS_STATEFP
# supposedly excluding them (4 HI counties, 22 of PR's 78 municipios, 1 of
# VI's 3 islands -- a sparse, partial, unexplained subset, not a clean
# territory inclusion). Zero AK/GU/AS/MP rows were found, so the exclusion
# isn't simply "not applied" -- something upstream (likely a BEA CAINC1
# regional-accounts join, given the raw/ directory's file names) is leaking
# a handful of non-CONUS rows through.
UNEXPECTED_NON_CONUS_IN_GEOREF = frozenset(
    {
        "15001",
        "15003",
        "15007",
        "15009",
        "72013",
        "72053",
        "72057",
        "72091",
        "72101",
        "72103",
        "72105",
        "72107",
        "72109",
        "72111",
        "72113",
        "72115",
        "72117",
        "72119",
        "72121",
        "72123",
        "72125",
        "72127",
        "72129",
        "72131",
        "72133",
        "72135",
        "78010",
    }
)

NON_CONUS_STATEFP = frozenset({"02", "15", "60", "66", "69", "72", "78"})


@dataclass(frozen=True, slots=True)
class Resolution:
    fips: str
    status: Status
    canonical_geoids: tuple[str, ...]
    shares: tuple[float, ...] | None
    note: str


def resolve(fips: str) -> Resolution:
    fips = str(fips).strip().zfill(5)
    counties = rpa_geo.load_counties()

    if fips in CT_DUPLICATE_NEW_REGIONS:
        return Resolution(
            fips,
            "ct_duplicate_direct",
            (fips,),
            None,
            "Present directly in georef.csv AND reachable by allocating one of CT's old 8 counties -- see CT_DUPLICATE_NEW_REGIONS. Don't sum this row together with its old-county predecessors' allocated shares.",
        )

    if fips in OLD_CT_COUNTY_FIPS:
        splits = rpa_geo.resolve_ct_old_county(fips)
        return Resolution(
            fips,
            "ct_allocation",
            tuple(s.successor_geoid for s in splits),
            tuple(s.share_of_predecessor for s in splits),
            "Connecticut's old-county-to-planning-region switch; see rpa_geo.splits.",
        )

    if fips in UNEXPECTED_NON_CONUS_IN_GEOREF:
        return Resolution(
            fips,
            "out_of_scope_but_present",
            (fips,) if fips in counties else (),
            None,
            "Non-CONUS per this repo's own NON_CONUS_STATEFP design, but present in georef.csv anyway -- see UNEXPECTED_NON_CONUS_IN_GEOREF. Reported upstream; not silently dropped here.",
        )

    if fips[:2] in NON_CONUS_STATEFP:
        return Resolution(
            fips,
            "out_of_scope_by_design",
            (),
            None,
            "Non-CONUS per NON_CONUS_STATEFP -- correctly out of scope for this repo, not a gap.",
        )

    if fips in counties:
        return Resolution(
            fips,
            "direct",
            (fips,),
            None,
            "CB-2021 and canonical 2025 share this GEOID directly (verified by full diff aside from CT).",
        )

    edge_target = rpa_geo.canonical_geoid(fips)
    if edge_target is not None:
        edge = rpa_geo.load_history_edges()[fips]
        return Resolution(fips, "history_edge", (edge_target,), None, edge.note)

    return Resolution(
        fips,
        "unresolved",
        (),
        None,
        "Not a canonical GEOID and not a known special case. Needs investigation.",
    )
