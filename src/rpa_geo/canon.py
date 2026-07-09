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


def data_path(name: str) -> importlib.resources.abc.Traversable:
    """Path to a shipped data file, for use by other modules in this package."""
    return importlib.resources.files(_DATA_PACKAGE) / name


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
class OutOfScopeCode:
    code: str
    label: str
    reason: str
    seen_in: str


def _read_csv(name: str) -> list[dict[str, str]]:
    text = data_path(name).read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))


@lru_cache(maxsize=1)
def load_counties() -> dict[str, County]:
    """The canonical current-vintage reference table, keyed by GEOID."""
    counties: dict[str, County] = {}
    for row in _read_csv("counties_2025.csv"):
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
