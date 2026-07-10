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
(``data/processed/georef.csv``) originally surfaced two anomalies (at
3,104 distinct fips): CT's 2 new-region rows double-counted alongside the
old 8 counties, and 27 non-CONUS rows despite the repo's own CONUS+DC
design. Both were **fixed at the source** in rpa-landuse-2030 PR #86
(merged ``bbbdd66``, closing issues #80/#81) by filtering
``nri_extractor._create_georef_from_transitions()`` to CONUS+DC and
dropping the 2 duplicate CT rows. Verified fixed against the live file as
of 2026-07-10 (now 3,075 distinct fips, zero of either anomaly). See
``CT_DUPLICATE_NEW_REGIONS`` / ``UNEXPECTED_NON_CONUS_IN_GEOREF`` below --
kept as empty, documented frozensets (not deleted), so ``resolve()``'s
corresponding statuses still catch a future regression instead of
silently missing one.

Re-validating surfaced a **third, differently-shaped** anomaly the first
pass couldn't see: ``resolve()`` and the live-data test only ever classify
fips values *present* in ``georef.csv`` -- neither has any way to notice a
canonically CONUS+DC GEOID that's entirely *absent*. A separate diff
against ``rpa_geo.load_counties()``'s full ``is_conus`` set found 35 such
gaps (DC, 2 Colorado consolidated city-counties, St. Louis City MO, and 31
Virginia county-equivalents -- see ``KNOWN_MISSING_CONUS_GEOIDS``).
Reported upstream as rpa-landuse-2030 issue #87; likely a longstanding NRI
survey-coverage gap for non-standard county-equivalents, not a #86
regression (see that issue for the reasoning).
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

# FIXED (2026-07-10, rpa-landuse-2030 PR #86 / issue #80): georef.csv used
# to have 2 new CT planning-region GEOIDs (Lower Connecticut River Valley
# 09130, Southeastern Connecticut 09180) present directly ALONGSIDE all 8
# old CT counties -- double-counting that area for anything summing every
# row without deduplicating CT. Dropped at the source in
# nri_extractor._create_georef_from_transitions(). Kept as an empty,
# documented frozenset (not deleted) so ct_duplicate_direct still fires on
# a regression rather than silently passing.
CT_DUPLICATE_NEW_REGIONS: frozenset[str] = frozenset()

# FIXED (2026-07-10, rpa-landuse-2030 PR #86 / issue #81): georef.csv used
# to have 27 non-CONUS GEOIDs (4 HI counties, 22 of PR's 78 municipios, 1
# of VI's 3 islands) despite the repo's own NON_CONUS_STATEFP design
# excluding them. Dropped at the source by filtering
# nri_extractor._create_georef_from_transitions() to CONUS+DC (reusing
# geo.py's own NON_CONUS_STATEFP). Kept as an empty, documented frozenset
# (not deleted) so out_of_scope_but_present still fires on a regression
# rather than silently passing.
UNEXPECTED_NON_CONUS_IN_GEOREF: frozenset[str] = frozenset()

# OPEN (rpa-landuse-2030 issue #87, filed 2026-07-10): 35 canonical
# CONUS+DC GEOIDs (per rpa_geo.load_counties()'s is_conus flag) have no row
# in georef.csv at all -- neither resolve() nor the live-data test below
# can catch this shape of gap, since both only ever classify fips values
# that ARE present. DC; Denver + Broomfield, CO (consolidated
# city-and-county governments); St. Louis City, MO (independent of any
# county); Arlington County + 30 of Virginia's independent cities. Likely
# a longstanding NRI survey-coverage gap for non-standard
# county-equivalents (georef.csv "was a passive byproduct of whatever fips
# happened to survive NRI extraction, not a deliberately curated
# reference" per issue #81) -- not a #86 regression. Flagged, not silently
# excluded from validation.
KNOWN_MISSING_CONUS_GEOIDS = frozenset(
    {
        "08014",
        "08031",
        "11001",
        "29510",
        "51013",
        "51510",
        "51520",
        "51530",
        "51540",
        "51570",
        "51580",
        "51590",
        "51595",
        "51600",
        "51610",
        "51620",
        "51630",
        "51640",
        "51660",
        "51670",
        "51678",
        "51683",
        "51685",
        "51690",
        "51700",
        "51720",
        "51730",
        "51735",
        "51750",
        "51770",
        "51775",
        "51790",
        "51820",
        "51830",
        "51840",
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
