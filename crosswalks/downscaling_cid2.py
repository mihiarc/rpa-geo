"""Crosswalk from rpa-socioeconomic-downscaling's ``cid2`` to rpa-geo's canonical GEOID.

``cid2`` is that repo's internal county key (see its ``constants.py::GEOID_RECODES``
and `data/raw/downscale_all_scenarios.do`). This module resolves every cid2 value
observed in that repo's live inputs (``importable19.xlsx`` + the HTF historical/
projected Excel files -- 3,197 distinct values as of 2026-07) to one of:

- a single canonical GEOID (most counties: cid2 already equals it, or a
  ``rpa_geo.history_edges`` 1:1 edge applies)
- an allocation across several canonical GEOIDs (CT's old counties, three AK
  Census Area splits -- see ``rpa_geo.splits``)
- a flagged Pacific placeholder (Guam resolves 1:1; American Samoa cannot,
  since cid2 carries it as a single row but Census recognizes 5 districts;
  Marshall Islands/Wake Island are out of scope, not real Census geography)
- an explicit "needs downscaling-repo-owner review" case, for the handful of
  legacy AK codes this module cannot responsibly resolve alone (see
  UNRESOLVED below)

Nothing here is silently dropped -- every code in the live universe resolves
to exactly one of the ``Resolution.status`` values, and the CSV export lists
every one of them explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import rpa_geo
from rpa_geo.splits import OLD_CT_COUNTY_FIPS

Status = Literal[
    "direct",  # cid2 IS the canonical GEOID already
    "history_edge",  # 1:1 legacy code, resolved via rpa_geo.history_edges
    "ct_allocation",  # CT's old 8 counties -> new 9 planning regions
    "ak_split_allocation",  # AK Census Area retirement/split
    "pacific_1to1",  # Guam: cid2 placeholder resolves cleanly to one canonical GEOID
    "pacific_unresolved",  # American Samoa: cid2 has 1 row, Census has 5 districts
    "out_of_scope",  # not real Census geography (Marshall Islands, Wake Island)
    "inert_placeholder",  # cid2's own data marks this empty/unused (e.g. "REMAINDER OF ALASKA")
    "unresolved_needs_review",  # genuine gap this module can't responsibly resolve alone
]


@dataclass(frozen=True, slots=True)
class Resolution:
    cid2: str
    status: Status
    canonical_geoids: tuple[str, ...]  # empty for out_of_scope/inert/unresolved
    shares: tuple[float, ...] | None  # None unless status is an allocation
    note: str


# American Samoa's 5 canonical districts, for the pacific_unresolved case.
_AMERICAN_SAMOA_DISTRICTS = ("60010", "60020", "60030", "60040", "60050")

# cid2 values this module cannot responsibly resolve without input from the
# downscaling repo's owner. "02231" is the deepest-legacy AK code observed
# (source data names it "Skagway-Yakutat-Angoon Census Area", populated for
# 1970-2022): it predates even the 2007 Skagway-Hoonah-Angoon split this
# package already models, and its further breakdown (Skagway + Hoonah-Angoon
# + a portion of Yakutat) isn't independently verified here.
UNRESOLVED_CID2: dict[str, str] = {
    "02231": (
        "Named 'Skagway-Yakutat-Angoon Census Area' in the repo's own `name` "
        "column; populated 1970-2022 in importable19. Predates the 2007 "
        "Skagway-Hoonah-Angoon split this package models (see "
        "rpa_geo.splits, case AK_skagway_hoonah_angoon_2007) -- its own "
        "further breakdown into current AK geography is not verified here."
    ),
}

# cid2 values the repo's own data marks as empty/inert (importable19's
# `dropthis` flag = 1 AND zero non-null population rows across all years).
INERT_CID2: dict[str, str] = {
    "02999": "Repo's own `name` column: 'REMAINDER OF ALASKA'. dropthis=1 in importable19, and zero non-null population rows across 1970-2100 -- an unused placeholder, not real geography.",
}


def resolve(cid2: str) -> Resolution:
    cid2 = str(cid2).strip().zfill(5)

    if cid2 in INERT_CID2:
        return Resolution(cid2, "inert_placeholder", (), None, INERT_CID2[cid2])

    if cid2 in UNRESOLVED_CID2:
        return Resolution(
            cid2, "unresolved_needs_review", (), None, UNRESOLVED_CID2[cid2]
        )

    out_of_scope = rpa_geo.load_out_of_scope()
    if cid2 in out_of_scope:
        return Resolution(cid2, "out_of_scope", (), None, out_of_scope[cid2].reason)

    if cid2 == "73001":  # Guam placeholder
        return Resolution(
            cid2,
            "pacific_1to1",
            ("66010",),
            None,
            "cid2 placeholder for Guam; Guam has exactly one Census county-equivalent (66010), so this is a clean 1:1 resolution.",
        )

    if cid2 == "74001":  # American Samoa placeholder
        return Resolution(
            cid2,
            "pacific_unresolved",
            _AMERICAN_SAMOA_DISTRICTS,
            None,
            "cid2 carries American Samoa as a single row, but Census recognizes 5 distinct county-equivalent districts. Cannot collapse to one canonical GEOID without population/area weights this module doesn't have (unlike CT, no town-level correspondence + weight source was located for AS in this pass).",
        )

    if cid2 in OLD_CT_COUNTY_FIPS:
        splits = rpa_geo.resolve_ct_old_county(cid2)
        return Resolution(
            cid2,
            "ct_allocation",
            tuple(s.successor_geoid for s in splits),
            tuple(s.share_of_predecessor for s in splits),
            "Connecticut's old-county-to-planning-region switch (2022); see rpa_geo.splits for methodology.",
        )

    ak_splits = rpa_geo.resolve_predecessor(cid2)
    if ak_splits:
        return Resolution(
            cid2,
            "ak_split_allocation",
            tuple(s.successor_geoid for s in ak_splits),
            tuple(s.share_of_predecessor for s in ak_splits),
            ak_splits[0].note,
        )

    edge_target = rpa_geo.canonical_geoid(cid2)
    if edge_target is not None:
        if edge_target == cid2:
            return Resolution(
                cid2,
                "direct",
                (cid2,),
                None,
                "cid2 already equals the canonical current GEOID.",
            )
        edge = rpa_geo.load_history_edges()[cid2]
        return Resolution(cid2, "history_edge", (edge_target,), None, edge.note)

    return Resolution(
        cid2,
        "unresolved_needs_review",
        (),
        None,
        "Not a canonical GEOID, not in history_edges, not a known split predecessor, and not a known special case. Needs investigation.",
    )
