# CLAUDE.md

`rpa-geo` (package `rpa_geo`) is the canonical county / county-equivalent reference for the
workspace, plus per-repo crosswalks. It does **not** migrate any repo's key scheme — each
consumer keeps its own (`cid2`, `county_fips`, `fips`) and resolves to canonical on demand.

`README.md` is the authoritative document: package data, crosswalks, findings and onboarding.
This file holds the rules.

## Rules

- **Never fan out `02070` (Dillingham) or `02290` (Yukon-Koyukuk) on current-vintage data.**
  Both are also ordinary current GEOIDs. Only 2015-scheme data (`cid2`) fans them out.
- **Rename directions need a primary source.** Check each one against real data; don't assume
  the naive higher-number-is-older pattern. Each `history_edges.csv` row's `source` column says
  how much to trust it, and `downscaling_cid2_specific` is not a verified retired Census FIPS.
- **Vintages sit side by side.** Add `counties_YYYY.csv` next to the old file; never overwrite.
- **Weight bases differ.** Land-area shares cover all of `historical_splits.csv`; population
  shares exist only for CT. Pick the basis that matches what you allocate.
- **Every crosswalk ships `validate_universe()`**, and each new `Status` goes into
  `rpa_geo.contracts.STATUS_CATEGORY` (a test enforces it).
- **`county-climate` has no crosswalk module.** It reads the canonical county table directly.

## rpa-landuse-2030 `georef.csv` anomalies

`landuse2030_fips.py` guards three known anomalies. Two guards are **empty, documented
frozensets**, kept so a regression re-fires: `CT_DUPLICATE_NEW_REGIONS` (Connecticut represented twice, old counties plus two new
planning regions) and `UNEXPECTED_NON_CONUS_IN_GEOREF` (non-CONUS rows in a CONUS+DC-only file).
`KNOWN_MISSING_CONUS_GEOIDS` lists canonical CONUS+DC GEOIDs (DC, Denver and Broomfield CO,
St. Louis City, Arlington County and Virginia independent cities) absent from `georef.csv`. `resolve()` only classifies values *present* in a file, so it can
never surface this shape of anomaly; find it by diffing the canonical `is_conus` set against the
live file. The module docstring and README carry the details.
