# CLAUDE.md

`rpa-geo` (package `rpa_geo`) is the canonical county / county-equivalent reference for the
workspace, plus per-repo crosswalks. It does **not** migrate any repo's key scheme — each
consumer keeps its own (`cid2`, `county_fips`, `fips`) and resolves to canonical on demand.

`README.md` is the authoritative document here; it carries the full per-repo crosswalk status
table and the findings write-ups. This file is the orientation layer.

## Reference data (`src/rpa_geo/data/`)

- **`counties_2025.csv`** — the join target. Census TIGER 2025, 3,235 rows, keyed on 5-digit
  `geoid`, with `is_conus` / `is_territory` flags.
- **`history_edges.csv`** — 28 1:1 edges from a prior/legacy GEOID to its current canonical
  GEOID. Each row's `source` column says how much to trust it: `census_official` (an
  individually verified Census rename/renumbering, with a citation in the note),
  `census_official_approximate` (a genuine Census change involving small annexed slivers this
  package doesn't allocate), or `downscaling_cid2_specific` (a code only known to be used
  internally by `rpa-socioeconomic-downscaling`'s `cid2` scheme — **not** a verified retired
  Census FIPS). Directions were verified one at a time against real data — don't assume the
  naive higher-number-is-older pattern holds.
- **`historical_splits.csv`** — GEOIDs that don't map 1:1, so there is only an allocation, not
  a single answer. Seven cases, 32 rows: Connecticut's 2022 planning-region switch
  (many-to-many, 19 rows, weighted both by town land area *and* by 2020 town population) plus
  six Alaska cases weighted by successors' current land area. **Two predecessor codes
  (`02070` Dillingham, `02290` Yukon-Koyukuk) are also ordinary current GEOIDs** — on
  current-vintage data they must pass straight through and must not be fanned out; only
  2015-scheme data (`cid2`) should fan them out.
- Also present: `census2015_link.csv`, `combinations_2015.csv` (combined reporting units in the
  2015 scheme; membership only, allocation is the consumer's choice), `locations_2015_ak.csv`,
  `out_of_scope.csv`.

## Crosswalks (`src/rpa_geo/crosswalks/`)

One module per consumer: `downscaling_cid2.py` (`cid2`), `slr_county_fips.py`
(`county_fips`; pure identity — TIGER 2024 and canonical 2025 share an identical GEOID
universe, verified by full diff), `landuse2030_fips.py` (`fips`), `data_portal_landuse.py`,
and `census2015.py` (canonical → `cid2`, the direction needed to feed `urban-rents` /
`rpa-slr` / `coastal-land-loss` outputs into Prestemon's Stata models). Each ships
`validate_universe()`.

`county-climate` reads the canonical county table directly (no crosswalk module). The other
consumers pin the released tag `v0.4.0`, except `rpa-socioeconomic-downscaling`, which uses a path
dependency.

## rpa-landuse-2030 `georef.csv` anomalies

`landuse2030_fips.py` guards three known anomalies. Two are fixed upstream (landuse-rpa-2030 #80
and #81, via PR #86), and their guards are kept as **empty, documented frozensets** so a regression
re-fires: `CT_DUPLICATE_NEW_REGIONS` (Connecticut represented twice, old counties plus two new
planning regions) and `UNEXPECTED_NON_CONUS_IN_GEOREF` (non-CONUS rows in a CONUS+DC-only file).
`KNOWN_MISSING_CONUS_GEOIDS` is **still open** (landuse-rpa-2030 #87): 35 canonical CONUS+DC GEOIDs
(DC, Denver and Broomfield CO, St. Louis City, Arlington County and 30 Virginia independent cities)
are absent from `georef.csv`. `resolve()` only classifies values *present* in a file, so it can
never surface this shape of anomaly; find it by diffing the canonical `is_conus` set against the
live file. The module docstring and README carry the details.
