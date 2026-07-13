"""Crosswalk from rpa-socioeconomic-downscaling's ``cid2`` to rpa-geo's canonical GEOID.

``cid2`` is that repo's internal county key (see its ``constants.py::GEOID_RECODES``
and `data/raw/downscale_all_scenarios.do`). This module resolves every cid2 value
observed in that repo's live inputs (``importable19.xlsx`` + the HTF historical/
projected Excel files -- 3,197 distinct values as of 2026-07) to one of:

- a single canonical GEOID (most counties: cid2 already equals it, or a
  ``rpa_geo.history_edges`` 1:1 edge applies)
- an allocation across several canonical GEOIDs (CT's old counties, three AK
  Census Area splits -- see ``rpa_geo.splits``)
- a Pacific placeholder resolved 1:1 (Guam -> 66010)
- a knowingly-dropped code (American Samoa: the downscaling owner elected not
  to model the territory on 2026-07-13; Marshall Islands / Wake Island are out
  of scope, not real Census geography)
- an explicit "needs downscaling-repo-owner review" case for any legacy code
  this module cannot responsibly resolve alone (currently none -- see
  UNRESOLVED below)

Nothing here is silently dropped -- every code in the live universe resolves
to exactly one of the ``Resolution.status`` values, and the CSV export lists
every one of them explicitly.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

import rpa_geo
from rpa_geo import contracts
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


# cid2 values this module cannot responsibly resolve without input from the
# downscaling repo's owner. Currently empty: the one former entry, "02231"
# ("Skagway-Yakutat-Angoon Census Area"), was resolved on 2026-07-13 when the
# repo owner (J. Prestemon) directed mapping it to Hoonah-Angoon (02105) -- now
# a downscaling_cid2_specific edge in history_edges.csv. A genuinely
# unresolvable code gets added back here (resolve() also has a catch-all).
UNRESOLVED_CID2: dict[str, str] = {}

# cid2 values safe to ignore for this repo: either the repo's own data marks
# them empty/inert (dropthis=1 AND zero non-null population rows), or the repo
# owner has explicitly elected not to model them.
INERT_CID2: dict[str, str] = {
    "02999": "Repo's own `name` column: 'REMAINDER OF ALASKA'. dropthis=1 in importable19, and zero non-null population rows across 1970-2100 -- an unused placeholder, not real geography.",
    "74001": "American Samoa. Census recognizes five districts (60010-60050); the repo carries it as a single row. The downscaling owner (J. Prestemon) elected not to model American Samoa on 2026-07-13, so it is knowingly excluded rather than fanned out to the five districts.",
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


def validate_universe(
    cid2_values: Iterable[str],
    *,
    allow: frozenset[contracts.Category] = contracts.RESOLVED_CATEGORIES,
) -> None:
    """Raise if any cid2 value resolves outside ``allow`` -- see rpa_geo.contracts.

    Call this at the panel's own ingest boundary, on the live cid2 universe,
    before any downstream code trusts it -- not just in a test that might
    not cover a value that only shows up in production data.
    """
    contracts.validate_universe(cid2_values, resolve, allow=allow)
