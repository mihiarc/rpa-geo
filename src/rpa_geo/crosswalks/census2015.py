"""The canonical link between current (2025) GEOIDs and the 2015-vintage scheme.

"2015 scheme" here means the county/county-equivalent scheme used by
J. Prestemon's Stata econometric models -- the same key
rpa-socioeconomic-downscaling carries as ``cid2``. It is *approximately*
Census 2015 FIPS, with three deliberate departures:

- **Alaska** uses 24 constant-geography locations (some predating even the
  2015 vintage), defined authoritatively by the owner's
  ``Alaska_locations_final.xlsx`` (received 2026-07-16, archived at
  ``~/Data/projects/rpa-geo/``, converted to
  ``data/census2015_link.csv`` + ``data/locations_2015_ak.csv``). They
  exactly partition all 30 current AK county-equivalents.
- **Connecticut** keeps the old 8 counties; the owner's
  ``ct_cou_to_cousub_crosswalk_final_choices.xlsx`` (same date) assigns each
  old county exactly ONE current planning region to read -- a deliberate 1:1
  simplification, NOT the weighted many-to-many allocation in
  ``rpa_geo.splits`` (which remains the right tool for allocating data, and
  is deliberately untouched by this module). Two regions (South Central
  09170, Western 09190) are never read; Capitol (09110) is read twice
  (Hartford + Tolland).
- **BEA-style combinations** merge some small county-equivalents into a
  neighbor under a 9xx code (VA's 24 county+independent-city combos, Maui+
  Kalawao 15901, Shawano+Menominee 55901). Combos with owner-confirmed
  COMPLETE membership (15901 and 55901, confirmed by the owner's 2026-07-30
  email; see ``rpa_geo.load_combinations_2015``) resolve every member here.
  For VA the owner's own ``GEOID_RECODES`` confirms only the principal
  county of each combo, so the 31 codes whose membership is NOT
  owner-confirmed (28 VA independent cities, La Paz 04012, Cibola 35006,
  Broomfield 08014 -- all younger than, or absorbed by, the
  constant-geography panel) are flagged ``membership_2015_unknown``, not
  guessed. Getting the VA city membership from the owner is the known
  remaining gap.

This is the crosswalk to use when feeding current-GEOID-keyed outputs
(urban rents, rpa-slr HTF, rpa-slr-landuse exposure shares) into the
2015-keyed Stata models. It answers "which 2015 location consumes this
current county's value" (``resolve``) and "which current counties feed this
2015 location" (``from_2015``). For the opposite problem -- resolving a live
``cid2`` panel *key* to canonical geography with allocation weights -- use
``rpa_geo.crosswalks.downscaling_cid2``.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import rpa_geo
from rpa_geo import contracts
from rpa_geo.canon import data_path

Status = Literal[
    "identity",  # same GEOID in the 2015 scheme and canonical 2025
    "renamed",  # 1:1 Census rename; the 2015 scheme retains the old code
    "ak_aggregate_member",  # member of one of the 24 owner-defined AK locations
    "ct_owner_assignment",  # CT planning region read by its assigned old county(-ies)
    "ct_owner_unassigned",  # CT planning region deliberately read by no old county
    "combo_member",  # owner-confirmed member of a BEA-style combination code
    "membership_2015_unknown",  # likely absorbed into a combo, but not owner-confirmed
    "owner_excluded",  # owner elected not to model this geography
    "pacific_placeholder",  # Guam -> the scheme's 73001 placeholder
    "territory_unmodeled",  # territory with no 2015-scheme counterpart or owner decision
    "not_canonical_2025",  # input is not a canonical 2025 GEOID at all
]


@dataclass(frozen=True, slots=True)
class Resolution:
    geoid_2025: str
    status: Status
    geoids_2015: tuple[str, ...]  # empty when nothing consumes this GEOID's value
    note: str


@dataclass(frozen=True, slots=True)
class AKLocation:
    """One of the 24 owner-defined AK locations, with his model attributes."""

    location_2015: str
    name: str
    coastal: bool
    intptlon: float
    intptlat: float


# Census renames where the 2015 scheme retains the OLD code, verified
# against the live cid2 universe (46113 present, 46102 absent). The Dade ->
# Miami-Dade rename (1997) is deliberately NOT here: the scheme already uses
# the current 12086. AK's two renames (02158->02270, 02198->02201) live in
# census2015_link.csv because the owner's AK file is their source.
RENAMED_IN_2015_SCHEME: dict[str, str] = {
    "46102": "46113",  # Oglala Lakota (May 2015) -- scheme retains Shannon County
}

# Canonical 2025 GEOIDs with no code of their own in the 2015 scheme, whose
# combination membership is NOT owner-confirmed. Verified by diffing the
# canonical table against the live cid2 universe (importable19.xlsx,
# 2026-07-16). BEA's county-combination definitions suggest where each
# belongs (e.g. each VA independent city into its adjacent county's 519xx
# combo, La Paz into Yuma, Cibola into Valencia; Broomfield didn't exist
# before 2001 and spans parts of four 2015 counties) -- but none of that is
# confirmed by the owner's files, so every one is flagged instead of
# guessed. Resolving these needs explicit confirmation from the owner.
# Kalawao 15005 and Shawano 55115 used to be here; the owner's 2026-07-30
# email confirmed their combos' complete membership (15901 = Maui+Kalawao,
# 55901 = Shawano+Menominee), so they now resolve as combo members via
# rpa_geo.load_combinations_2015.
MEMBERSHIP_2015_UNKNOWN: frozenset[str] = frozenset(
    {
        "04012",  # La Paz, AZ (created 1983)
        "08014",  # Broomfield, CO (created 2001, from parts of 4 counties)
        "35006",  # Cibola, NM (created 1981)
        # VA independent cities absent from the live cid2 universe:
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
        "51680",
        "51683",
        "51685",
        "51690",
        "51720",
        "51730",
        "51735",
        "51750",
        "51775",
        "51790",
        "51820",
        "51830",
        "51840",
    }
)

_AS_STATEFP = "60"  # American Samoa: owner elected not to model (2026-07-13)
_MP_STATEFP = "69"  # Northern Mariana Islands: no counterpart, no owner decision
_GUAM_GEOID = "66010"


def _read_data_csv(name: str) -> list[dict[str, str]]:
    text = data_path(name).read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))


@lru_cache(maxsize=1)
def _link_rows() -> dict[str, tuple[dict[str, str], ...]]:
    """census2015_link.csv rows grouped by geoid_2025 (09110 has two)."""
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in _read_data_csv("census2015_link.csv"):
        grouped.setdefault(row["geoid_2025"], []).append(row)
    return {k: tuple(v) for k, v in grouped.items()}


@lru_cache(maxsize=1)
def _combo_by_member() -> dict[str, tuple[str, str]]:
    """Owner-confirmed combination membership: current GEOID -> (combo, note).

    Two sources, merged. The ``downscaling_cid2_specific`` history edges map
    each VA combo code to its principal current county (e.g. 51901 -> 51003);
    reversed, they say which combo consumes that county's value -- a
    direction additionally confirmed by the downscaling repo's own
    ``GEOID_RECODES``. Combos with owner-confirmed COMPLETE membership
    (15901, 55901 -- see ``rpa_geo.load_combinations_2015``) contribute every
    member, not just the principal. After the 02231 edge's supersession
    there are no AK edges left in this set -- AK membership comes from
    census2015_link.csv instead.
    """
    members = {
        edge.canonical_geoid: (edge.legacy_geoid, edge.note)
        for edge in rpa_geo.load_history_edges().values()
        if edge.source == "downscaling_cid2_specific"
    }
    for combo, rows in rpa_geo.load_combinations_2015().items():
        for row in rows:
            members[row.member_geoid_2025] = (combo, row.note)
    return members


@lru_cache(maxsize=1)
def ak_locations() -> dict[str, AKLocation]:
    """The 24 owner-defined AK locations, keyed by 2015 location code.

    Attributes come verbatim from ``Alaska_locations_final.xlsx`` (names as
    the owner wrote them, his ``coastal`` model flag, and the Census interior
    point). The interior point legitimately crosses the antimeridian for
    Aleutians West (positive longitude); the source file's separate ``_CX``/
    ``_CY`` centroid columns were dropped because that pair is an
    antimeridian artifact there (a centroid in the eastern hemisphere).
    """
    return {
        row["location_2015"]: AKLocation(
            location_2015=row["location_2015"],
            name=row["name"],
            coastal=row["coastal"] == "1",
            intptlon=float(row["intptlon"]),
            intptlat=float(row["intptlat"]),
        )
        for row in _read_data_csv("locations_2015_ak.csv")
    }


def resolve(geoid_2025: str) -> Resolution:
    """Which 2015-scheme location(s) consume this current GEOID's value.

    AK ``ak_aggregate_member`` targets want the member's value *aggregated*
    into the location (with its fellow members); CT ``ct_owner_assignment``
    targets each want the region's value *replicated* (09110 feeds both
    Hartford and Tolland; nothing is split). Everything else is 1:1 or
    deliberately unconsumed.
    """
    geoid_2025 = str(geoid_2025).strip().zfill(5)

    link = _link_rows().get(geoid_2025)
    if link is not None:
        status = link[0]["relationship"]
        targets = tuple(row["geoid_2015"] for row in link if row["geoid_2015"])
        if status == "identity":
            # Same code either side, but keep the link CSV as the source of
            # truth for which AK codes the owner's file lists as unchanged.
            return Resolution(geoid_2025, "identity", targets, link[0]["note"])
        return Resolution(
            geoid_2025,
            status,  # type: ignore[arg-type]  # validated by tests against Status
            targets,
            " / ".join(dict.fromkeys(row["note"] for row in link)),
        )

    if geoid_2025 in RENAMED_IN_2015_SCHEME:
        return Resolution(
            geoid_2025,
            "renamed",
            (RENAMED_IN_2015_SCHEME[geoid_2025],),
            "Census renamed this county; the 2015 scheme retains the old code "
            "(verified against the live cid2 universe).",
        )

    combo = _combo_by_member().get(geoid_2025)
    if combo is not None:
        combo_code, combo_note = combo
        return Resolution(
            geoid_2025,
            "combo_member",
            (combo_code,),
            f"Owner-confirmed member of combination code {combo_code}: {combo_note}",
        )

    if geoid_2025 in MEMBERSHIP_2015_UNKNOWN:
        return Resolution(
            geoid_2025,
            "membership_2015_unknown",
            (),
            "No code of its own in the 2015 scheme, and its combination "
            "membership is not owner-confirmed -- see MEMBERSHIP_2015_UNKNOWN. "
            "Needs a third crosswalk file (or explicit confirmation) from the "
            "owner; do not guess.",
        )

    counties = rpa_geo.load_counties()
    if geoid_2025 not in counties:
        return Resolution(
            geoid_2025,
            "not_canonical_2025",
            (),
            "Not a canonical 2025 GEOID -- this crosswalk starts from current "
            "geography. For resolving a live cid2 key, use "
            "rpa_geo.crosswalks.downscaling_cid2 instead.",
        )

    if geoid_2025.startswith(_AS_STATEFP):
        return Resolution(
            geoid_2025,
            "owner_excluded",
            (),
            "American Samoa: the owner elected not to model the territory "
            "(2026-07-13), so its districts are knowingly unconsumed.",
        )

    if geoid_2025 == _GUAM_GEOID:
        return Resolution(
            geoid_2025,
            "pacific_placeholder",
            ("73001",),
            "Guam's value feeds the scheme's 73001 placeholder (present in the "
            "downscaling repo's HTF inputs, not the econometric panel itself).",
        )

    if geoid_2025.startswith(_MP_STATEFP):
        return Resolution(
            geoid_2025,
            "territory_unmodeled",
            (),
            "Northern Mariana Islands: no 2015-scheme counterpart and no "
            "documented owner decision -- a genuine gap, flagged rather than "
            "silently dropped.",
        )

    return Resolution(
        geoid_2025,
        "identity",
        (geoid_2025,),
        "Same GEOID in the 2015 scheme and canonical 2025.",
    )


FromKind = Literal[
    "identity",  # the location IS a current canonical GEOID
    "renamed_current",  # 1:1 rename -- read the current code's value
    "ak_aggregate",  # aggregate the member counties' values
    "ct_assigned_region",  # copy the assigned planning region's value
    "combo",  # owner-confirmed member(s) only -- see the membership gap note
    "pacific_placeholder",  # 73001 -> Guam
    "unknown_2015_code",  # not a location the 2015 scheme defines
]


@dataclass(frozen=True, slots=True)
class Location2015:
    geoid_2015: str
    kind: FromKind
    geoids_2025: tuple[str, ...]
    note: str


@lru_cache(maxsize=1)
def _members_by_location() -> dict[str, tuple[str, ...]]:
    members: dict[str, list[str]] = {}
    for row in _read_data_csv("census2015_link.csv"):
        if row["geoid_2015"]:
            members.setdefault(row["geoid_2015"], []).append(row["geoid_2025"])
    return {k: tuple(v) for k, v in members.items()}


def from_2015(geoid_2015: str) -> Location2015:
    """Which current (2025) GEOIDs feed one 2015-scheme location.

    The inverse view of ``resolve``: aggregate the returned counties for an
    AK location, or read the single returned region/county elsewhere. For
    combination codes this returns only the owner-confirmed members (the
    unconfirmed ones are the ``MEMBERSHIP_2015_UNKNOWN`` gap and are *not*
    silently included).
    """
    geoid_2015 = str(geoid_2015).strip().zfill(5)

    link_members = _members_by_location().get(geoid_2015)
    if link_members is not None:
        rel = _link_rows()[link_members[0]][0]["relationship"]
        if rel == "ct_owner_assignment":
            # CT locations are keyed by old county; find this county's region.
            region = tuple(
                row["geoid_2025"]
                for g in link_members
                for row in _link_rows()[g]
                if row["geoid_2015"] == geoid_2015
            )
            return Location2015(
                geoid_2015,
                "ct_assigned_region",
                region,
                "Owner's final 1:1 choice -- copy this planning region's value.",
            )
        if len(link_members) > 1:
            return Location2015(
                geoid_2015,
                "ak_aggregate",
                link_members,
                "Aggregate these current counties' values, per the owner's "
                "Alaska_locations_final.xlsx.",
            )
        kind: FromKind = (
            "identity" if link_members[0] == geoid_2015 else "renamed_current"
        )
        return Location2015(
            geoid_2015, kind, link_members, _link_rows()[link_members[0]][0]["note"]
        )

    if geoid_2015 in RENAMED_IN_2015_SCHEME.values():
        current = next(
            g for g, old in RENAMED_IN_2015_SCHEME.items() if old == geoid_2015
        )
        return Location2015(
            geoid_2015,
            "renamed_current",
            (current,),
            "Census renamed this county -- read the current code's value.",
        )

    confirmed_combo = rpa_geo.load_combinations_2015().get(geoid_2015)
    if confirmed_combo:
        return Location2015(
            geoid_2015,
            "combo",
            tuple(m.member_geoid_2025 for m in confirmed_combo),
            "Owner-confirmed COMPLETE membership (2026-07-30), principal "
            "first -- aggregate these counties' values; the owner splits the "
            "combined values apart by population share in his own code.",
        )

    combo_members = tuple(
        member
        for member, (combo_code, _) in _combo_by_member().items()
        if combo_code == geoid_2015
    )
    if combo_members:
        return Location2015(
            geoid_2015,
            "combo",
            combo_members,
            "Owner-confirmed member(s) only. This combination likely also "
            "absorbs codes in MEMBERSHIP_2015_UNKNOWN (e.g. a VA independent "
            "city) -- that membership is a known gap, not included here.",
        )

    if geoid_2015 == "73001":
        return Location2015(
            geoid_2015, "pacific_placeholder", (_GUAM_GEOID,), "Guam placeholder."
        )

    if geoid_2015 in rpa_geo.load_counties():
        return Location2015(
            geoid_2015,
            "identity",
            (geoid_2015,),
            "Same GEOID in the 2015 scheme and canonical 2025.",
        )

    return Location2015(
        geoid_2015,
        "unknown_2015_code",
        (),
        "Not a location this 2015 scheme defines (nor a current GEOID). Legacy "
        "panel-only codes like 02232/02999 are deliberately not locations -- "
        "the owner's final AK file excludes them; see "
        "rpa_geo.crosswalks.downscaling_cid2 for resolving live panel keys.",
    )


def validate_universe(
    geoid_2025_values: Iterable[str],
    *,
    allow: frozenset[contracts.Category] = contracts.RESOLVED_CATEGORIES,
) -> None:
    """Raise if any current GEOID resolves outside ``allow`` -- see rpa_geo.contracts.

    Call this on the county universe of an output you're about to hand to
    the 2015-keyed Stata models. With the default ``allow``, the 31
    ``membership_2015_unknown`` codes (and MP's ``territory_unmodeled``)
    fail loudly -- appropriate, because e.g. VA's coastal independent cities
    genuinely have nowhere confirmed to go yet.
    """
    contracts.validate_universe(geoid_2025_values, resolve, allow=allow)
