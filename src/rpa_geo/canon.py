"""Canonical county/county-equivalent reference (TIGER/Line 2025 vintage).

See README.md for scope and provenance. Nothing here mutates any consuming
repo's data -- these are read-only lookups against the shipped CSVs in
``data/``.
"""

from __future__ import annotations

import csv
import importlib.resources
import io
from dataclasses import dataclass
from functools import lru_cache

Territory = str  # a 2-letter USPS code, e.g. "PR", "GU", "AS", "MP", "VI"

_DATA_PACKAGE = "rpa_geo.data"
_VINTAGE_PREFIX = "counties_"
_VINTAGE_SUFFIX = ".csv"


def data_path(name: str) -> importlib.resources.abc.Traversable:
    """Path to a shipped data file, for use by other modules in this package."""
    return importlib.resources.files(_DATA_PACKAGE) / name


def available_vintages() -> tuple[str, ...]:
    """Vintages shipped in this package, discovered from ``counties_*.csv``.

    Onboarding a new vintage (see README.md) is adding a new
    ``counties_YYYY.csv`` file -- this list, and ``LATEST_VINTAGE``, update
    themselves from that alone, no code change required.
    """
    names = (
        p.name
        for p in importlib.resources.files(_DATA_PACKAGE).iterdir()
        if p.name.startswith(_VINTAGE_PREFIX) and p.name.endswith(_VINTAGE_SUFFIX)
    )
    return tuple(
        sorted(name[len(_VINTAGE_PREFIX) : -len(_VINTAGE_SUFFIX)] for name in names)
    )


LATEST_VINTAGE = max(available_vintages())


@dataclass(frozen=True, slots=True)
class County:
    geoid: str
    name: str
    namelsad: str
    stusps: str
    state_name: str
    statefp: str
    countyfp: str
    countyns: str
    lsad: str
    aland_sqm: int
    awater_sqm: int
    is_conus: bool
    is_territory: bool


@dataclass(frozen=True, slots=True)
class HistoryEdge:
    legacy_geoid: str
    canonical_geoid: str
    state: str
    note: str
    source: str  # "census_official" | "downscaling_cid2_specific"


@dataclass(frozen=True, slots=True)
class Combination2015:
    """One member of an owner-confirmed BEA-style combined reporting unit.

    The 2015-vintage scheme used by J. Prestemon's Stata models carries a few
    9xx codes whose value covers SEVERAL current counties combined (BEA-style
    combined reporting). Unlike a ``HistoryEdge`` (structurally 1:1) or a
    ``Split`` (weighted allocation), a combination states *membership only* --
    the allocation basis (population, income, land area) is the consumer's
    choice, and the owner splits these apart by population share in his own
    code. Only combinations whose complete membership the owner has confirmed
    live here; VA's 24 county+city combos stay as principal-only history
    edges until he confirms which city belongs to which combo.
    """

    combo_2015: str
    member_geoid_2025: str
    principal: bool
    state: str
    note: str
    source: str


@dataclass(frozen=True, slots=True)
class OutOfScopeCode:
    code: str
    label: str
    reason: str
    seen_in: str


def _read_csv(name: str) -> list[dict[str, str]]:
    text = data_path(name).read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))


@lru_cache(maxsize=None)
def load_counties(vintage: str = LATEST_VINTAGE) -> dict[str, County]:
    """The canonical reference table for ``vintage``, keyed by GEOID.

    Defaults to ``LATEST_VINTAGE``. Vintages are shipped side-by-side (see
    ``available_vintages()``), not overwritten in place, so a consumer that
    isn't ready to move to a new Census vintage can keep pinning an older
    one explicitly instead of being forced to move in lockstep with every
    other consumer the moment this package adds one.
    """
    if vintage not in available_vintages():
        raise ValueError(
            f"No counties_{vintage}.csv shipped in this rpa-geo version. "
            f"Available vintages: {available_vintages()}."
        )
    counties: dict[str, County] = {}
    for row in _read_csv(f"counties_{vintage}.csv"):
        counties[row["geoid"]] = County(
            geoid=row["geoid"],
            name=row["name"],
            namelsad=row["namelsad"],
            stusps=row["stusps"],
            state_name=row["state_name"],
            statefp=row["statefp"],
            countyfp=row["countyfp"],
            countyns=row["countyns"],
            lsad=row["lsad"],
            aland_sqm=int(row["aland_sqm"]),
            awater_sqm=int(row["awater_sqm"]),
            is_conus=row["is_conus"] == "True",
            is_territory=row["is_territory"] == "True",
        )
    return counties


@lru_cache(maxsize=1)
def load_combinations_2015() -> dict[str, tuple[Combination2015, ...]]:
    """Owner-confirmed combined-reporting-unit membership, keyed by combo code.

    Members are ordered principal first. Every combo here has its COMPLETE
    membership confirmed by the owner (see each row's ``source``); a combo
    with only its principal member known does not belong in this table.
    """
    combos: dict[str, list[Combination2015]] = {}
    for row in _read_csv("combinations_2015.csv"):
        combos.setdefault(row["combo_2015"], []).append(
            Combination2015(
                combo_2015=row["combo_2015"],
                member_geoid_2025=row["member_geoid_2025"],
                principal=row["principal"] == "1",
                state=row["state"],
                note=row["note"],
                source=row["source"],
            )
        )
    return {
        combo: tuple(sorted(members, key=lambda m: not m.principal))
        for combo, members in combos.items()
    }


@lru_cache(maxsize=1)
def load_history_edges() -> dict[str, HistoryEdge]:
    """1:1 legacy-GEOID -> canonical-GEOID edges, keyed by legacy GEOID."""
    edges: dict[str, HistoryEdge] = {}
    for row in _read_csv("history_edges.csv"):
        edges[row["legacy_geoid"]] = HistoryEdge(
            legacy_geoid=row["legacy_geoid"],
            canonical_geoid=row["canonical_geoid"],
            state=row["state"],
            note=row["note"],
            source=row["source"],
        )
    return edges


@lru_cache(maxsize=1)
def load_out_of_scope() -> dict[str, OutOfScopeCode]:
    """Codes seen in the wild that are not real Census geography, keyed by code."""
    codes: dict[str, OutOfScopeCode] = {}
    for row in _read_csv("out_of_scope.csv"):
        codes[row["code"]] = OutOfScopeCode(
            code=row["code"],
            label=row["label"],
            reason=row["reason"],
            seen_in=row["seen_in"],
        )
    return codes


# Census lsad "25" = "city (independent)" -- Baltimore MD, St. Louis MO, and
# every one of Virginia's independent cities are coded this way in the
# source cartographic file (verified by direct inspection of
# counties_2025.csv: all 40 lsad="25" rows are exactly these, no others).
# Mechanically derivable, so not hand-curated.
_INDEPENDENT_CITY_LSAD = "25"

# Consolidated city-county governments and the federal district aren't
# distinguished from an ordinary county by any single field in the source
# extract -- Denver and Broomfield, CO both carry the ordinary county lsad
# "06" (shared with ~3,000 unrelated rows); DC carries "00", shared with
# unrelated territory placeholders (Guam, two uninhabited AS islands).
# Verified by direct inspection, not assumed -- hand-curated and cited here,
# the same discipline history_edges.csv uses for edges that can't be
# mechanically derived either.
CONSOLIDATED_CITY_COUNTY_GEOIDS: frozenset[str] = frozenset(
    {
        "08031",  # Denver, CO -- consolidated City and County of Denver
        "08014",  # Broomfield, CO -- consolidated City and County of Broomfield (2001)
        "32510",  # Carson City, NV -- consolidated city-county, independent of any county
        "11001",  # District of Columbia -- federal district, not a county or a city
    }
)


@lru_cache(maxsize=None)
def nonstandard_county_equivalents(vintage: str = LATEST_VINTAGE) -> frozenset[str]:
    """GEOIDs whose real-world shape commonly breaks code that assumes every
    place nests under exactly one ordinary "county" parent: independent
    cities, consolidated city-county governments, and DC.

    This is *not* a completeness check -- a GEOID can be a perfectly
    ordinary county (e.g. Arlington, VA) and still be missing from some
    repo's own reference table for an unrelated reason (see
    ``rpa-landuse-2030`` issue #87, where Arlington's absence was one of 35
    missing GEOIDs but not one of this shape). Use ``load_counties()``'s
    ``is_conus`` flag to check completeness; use this to check whether your
    own ingestion code even handles this shape at all, before it ships and
    a repo rediscovers the gap the way issue #87 did.
    """
    independent_cities = frozenset(
        geoid
        for geoid, county in load_counties(vintage).items()
        if county.lsad == _INDEPENDENT_CITY_LSAD
    )
    return independent_cities | CONSOLIDATED_CITY_COUNTY_GEOIDS


def canonical_geoid(geoid: str) -> str | None:
    """Resolve a GEOID (current or legacy) to its canonical current GEOID.

    Returns None if the GEOID is neither a current canonical GEOID nor a
    known legacy code. Does not handle the CT old-county many-to-many case
    (see ``rpa_geo.ct``) or American Samoa's 1-to-5 case -- both require an
    allocation, not a single answer.
    """
    geoid = geoid.strip().zfill(5)
    if geoid in load_counties():
        return geoid
    edge = load_history_edges().get(geoid)
    if edge is not None:
        return edge.canonical_geoid
    return None
