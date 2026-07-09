# rpa-geo

Canonical US county/county-equivalent reference for the `rpa-*` pipeline
repos, plus a crosswalk from each repo's current county key to that
canonical reference.

This package does **not** migrate any repo's internal county key. Each repo
keeps its own scheme (`cid2`, `county_fips`, `fips`, ...) and adopts the
canonical reference at its own pace via the crosswalk built for it.

## Canonical reference

- **Vintage:** Census TIGER/Line 2025 (current release as of this writing),
  sourced from the generalized `cb_2025_us_county_500k` cartographic
  boundary file (attributes only -- no geometry is shipped).
- **Scope:** the Census Bureau's full "counties and equivalents" universe --
  50 states + DC + Puerto Rico + US Virgin Islands + Guam + American Samoa +
  Northern Mariana Islands. 3,235 rows. Explicitly excludes the Marshall
  Islands and Wake Island, which are not Census-recognized county-equivalent
  geography (see `out_of_scope.csv`).
- **Key:** `geoid`, the current 5-digit Census FIPS/GEOID string.

## Package data (`src/rpa_geo/data/`)

| File | Contents |
|---|---|
| `counties_2025.csv` | The canonical reference table: one row per current county/equivalent, with `is_conus` and `is_territory` flags. |
| `history_edges.csv` | 1:1 edges from a prior/legacy GEOID to its current canonical GEOID -- 30 edges. Each is tagged in its `source` column: `census_official` (a genuine, individually verified Census Bureau rename/renumbering -- see each note for the specific citation), `census_official_approximate` (a genuine Census change involving small annexed slivers this package doesn't allocate -- see the note), or `downscaling_cid2_specific` (a code that's only known to be used internally by rpa-socioeconomic-downscaling's `cid2` scheme; **not** a verified retired Census FIPS). Directions were verified one at a time against real data (see "A direction bug we caught" below) -- don't assume the naive higher-number-is-older pattern holds. |
| `historical_splits.csv` | GEOIDs that don't map 1:1 to canonical -- they were divided among several current counties, so there's only an allocation, not a single answer. Four cases, 25 rows: Connecticut's 2022 planning-region switch (many-to-many, 19 rows, town-land-area-weighted) and three Alaska Census Area retirements that are clean 2-way splits (Wrangell-Petersburg 2008, Skagway-Hoonah-Angoon 2007, Valdez-Cordova 2019 -- each weighted by the current land area of its two successors). |
| `out_of_scope.csv` | Codes seen in the wild that are not real Census geography at all, with the reason (Marshall Islands, Wake Island). |

## Why area-weighted, not population-weighted, for the split allocations

Town-level 2020 population by county subdivision requires a Census API key
(`api.census.gov` now rejects unauthenticated requests). Land area doesn't.
Shipping the area-weighted version now and swapping in population weights
later (once a key is available, via `CENSUS_API_KEY` env var, never
hardcoded) is a strict improvement, not a redo -- the table schema already
has room for a second weight column.

## A direction bug we caught by validating against real data

Shannon County, SD was renamed Oglala Lakota County in 2015 -- but the FIPS
code moved from **46113 down to 46102**, the reverse of every other
rename in this package (Wade Hampton -> Kusilvak went 02270 -> 02158, a
higher-to-lower-looking but actually just "old code retired, new code
assigned" change with no numeric pattern to lean on). Trained-knowledge
recall got this backwards on the first pass; it was only caught by
round-tripping rpa-socioeconomic-downscaling's actual live `cid2` values
against this package's data and finding `46113` unresolved when it should
have resolved cleanly. The lesson generalizes: don't trust an assumed
direction for a GEOID rename without checking a primary source (this
package's history notes cite one per edge) or the consuming repo's live
data.

## Per-repo crosswalks (`crosswalks/`)

| Repo | Key | Module | Status |
|---|---|---|---|
| rpa-socioeconomic-downscaling | `cid2` | `downscaling_cid2.py` | All 3,197 live values resolve to an explicit status; 2 flagged for owner review (see findings below). |
| rpa-slr / rpa-slr-landuse | `county_fips` | `slr_county_fips.py` | Pure identity mapping -- TIGER 2024 and canonical 2025 share an identical GEOID universe, verified by full diff. |
| rpa-landuse-2030 | `fips` | `landuse2030_fips.py` | All 3,104 live `georef.csv` values resolve; 2 anomalies found and flagged (see findings below), reported upstream. |
| rpa-data-portal | n/a | `data_portal_landuse.py` | Documentation only, no resolve() -- the ETL only ever aggregates to state (`county[:2]`), never publishes a county-level GEOID itself, so old/new CT is a non-issue there today. Source JSON wasn't available locally to validate further. |

## Findings surfaced while building these crosswalks

Each of these was caught by validating against a repo's *live* data, not by
inspection -- the general lesson (see "A direction bug we caught" above)
generalizes across all four:

- **A second real historical gap**: Dade County, FL was renamed Miami-Dade
  County in 1997 (FIPS 12025 -> 12086) -- found via rpa-landuse-2030's
  `georef.csv`, not anticipated from the downscaling repo alone. Now in
  `history_edges.csv`.
- **`cid2=02261` (Valdez-Cordova) isn't in downscaling's `GEOID_RECODES` at
  all.** That list was built against the 2015 TIGER shapefile; Valdez-Cordova
  wasn't split into Chugach (02063) / Copper River (02066) until January
  2019, so the gap is expected, not a bug in that repo. Now covered by
  `historical_splits.csv`.
- **`cid2=02231`** ("Skagway-Yakutat-Angoon Census Area" per
  rpa-socioeconomic-downscaling's own `name` column, populated 1970-2022) is
  a *deeper* legacy code than anything else in this package -- it predates
  even the 2007 Skagway-Hoonah-Angoon split. We couldn't independently
  verify its further breakdown into current AK geography, so it's flagged
  `unresolved_needs_review` in `crosswalks/downscaling_cid2.py` rather than
  guessed. Same for `cid2=02999` ("REMAINDER OF ALASKA", `dropthis=1` and
  zero non-null population rows in the source panel) -- flagged
  `inert_placeholder`, not silently dropped.
- **rpa-landuse-2030's `georef.csv` represents part of Connecticut twice.**
  It has all 8 old counties *and* 2 of the 9 new planning regions (Lower
  Connecticut River Valley 09130, Southeastern Connecticut 09180) as
  independent rows. Middlesex/New London/part of Windham allocate into those
  same 2 regions, so summing every row without deduplicating CT double-counts
  that area. Flagged `ct_duplicate_direct`, reported upstream.
- **rpa-landuse-2030's `georef.csv` has 27 non-CONUS rows despite its own
  documented CONUS+DC-only design** (`NON_CONUS_STATEFP`): 4 of HI's 5
  counties, 22 of PR's 78 municipios, 1 of VI's 3 islands, and zero AK/GU/AS/MP
  -- a sparse, partial, unexplained leak (possibly from a BEA CAINC1
  regional-accounts join, given the `data/raw/` file names), not a clean
  territory inclusion. Flagged `out_of_scope_but_present`, reported upstream.

## Onboarding a new repo

1. Load `counties_2025.csv` as your join target.
2. If your data uses any GEOID in `history_edges.csv`'s `legacy_geoid`
   column, join through it to canonical first.
3. If your data uses a GEOID in `historical_splits.csv`'s
   `predecessor_geoid` column (CT's old counties, or one of the three AK
   splits), decide whether you need a 1:1 approximation (pick the
   `successor_geoid` with the largest `share_of_predecessor`) or a true
   split (fan out by `share_of_predecessor` / `share_of_new_region`
   depending on direction).
4. Check any GEOID you can't resolve against `out_of_scope.csv` before
   assuming it's a bug in this package.
5. Add a per-repo crosswalk under `crosswalks/` in this repo (see
   `crosswalks/downscaling_cid2.py` for the pattern) and a test that
   round-trips every county in your live dataset to exactly one canonical
   row. Flag anything you can't responsibly resolve rather than guessing --
   see the AK findings above for what that looks like in practice.

Add as a dependency from a consuming repo with:

```bash
uv add --editable ../rpa-geo
```
