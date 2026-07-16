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

Vintages are shipped **side-by-side**, not overwritten in place --
`counties_2025.csv` today, `counties_2031.csv` alongside it once TIGER-2031+
is onboarded, and so on. `rpa_geo.load_counties()` defaults to
`rpa_geo.LATEST_VINTAGE`, but takes an explicit `vintage=` argument, and
`rpa_geo.available_vintages()` discovers every vintage this package version
ships (from the `counties_*.csv` filenames present -- no per-vintage code
change needed). This means a consuming repo isn't forced to move onto a new
Census vintage the moment this package adds one; it can keep pinning an
older vintage explicitly until it's ready. See "Onboarding a new vintage"
below for how a new one gets added.

## Package data (`src/rpa_geo/data/`)

| File | Contents |
|---|---|
| `counties_2025.csv` | The canonical reference table for the 2025 vintage: one row per current county/equivalent, with `is_conus` and `is_territory` flags. A future vintage bump adds `counties_YYYY.csv` alongside this file, not in place of it. |
| `history_edges.csv` | 1:1 edges from a prior/legacy GEOID to its current canonical GEOID -- 30 edges. Each is tagged in its `source` column: `census_official` (a genuine, individually verified Census Bureau rename/renumbering -- see each note for the specific citation), `census_official_approximate` (a genuine Census change involving small annexed slivers this package doesn't allocate -- see the note), or `downscaling_cid2_specific` (a code that's only known to be used internally by rpa-socioeconomic-downscaling's `cid2` scheme; **not** a verified retired Census FIPS). Directions were verified one at a time against real data (see "A direction bug we caught" below) -- don't assume the naive higher-number-is-older pattern holds. |
| `historical_splits.csv` | GEOIDs that don't map 1:1 to canonical -- they were divided among several current counties, so there's only an allocation, not a single answer. Seven cases, 32 rows: Connecticut's 2022 planning-region switch (many-to-many, 19 rows, weighted both by town land area *and* by 2020 town population -- see below) and six Alaska cases, each weighted by the current land area of its successors: three Census Area retirements (Wrangell-Petersburg 2008, Skagway-Hoonah-Angoon 2007, Valdez-Cordova 2019), the deeper Skagway-Yakutat-Angoon retirement (1992, expressed directly against its three *current* successors), and two boundary-shrink cases where **the predecessor code is also a current GEOID** (Dillingham 02070 lost Lake and Peninsula in 1989; Yukon-Koyukuk 02290 lost Denali in 1990) -- on current-vintage data those two codes are ordinary counties and must not be fanned out; the split rows describe the pre-shrink combined areas, which is what rpa-socioeconomic-downscaling's `cid2` means by them per the owner's `Alaska_locations_final.xlsx` (2026-07-16). |
| `census2015_link.csv` | The canonical link between current (2025) GEOIDs and the 2015-vintage scheme used by J. Prestemon's Stata econometric models, for the two states where the schemes diverge structurally (AK 30 rows, CT 10 rows). Converted from the owner's two final crosswalk files (received 2026-07-16, archived at `~/Data/projects/rpa-geo/`); consumed by `crosswalks/census2015.py` -- see "The canonical 2025 <-> 2015 link" below. |
| `locations_2015_ak.csv` | The owner's 24 Alaska model locations with his attributes (name as he wrote it, `coastal` flag, Census interior point). The source file's `_CX`/`_CY` centroid columns were dropped: they're an antimeridian artifact for Aleutians West (a centroid in the eastern hemisphere); the interior-point columns handle the antimeridian correctly (positive longitude). |
| `out_of_scope.csv` | Codes seen in the wild that are not real Census geography at all, with the reason (Marshall Islands, Wake Island). |

## Area- and population-weighted split allocations

`historical_splits.csv` carries **two independent weight bases per row**,
so consumers pick whichever is appropriate for what they're allocating:

- `weight_basis` / `share_of_predecessor` / `share_of_new_region` --
  land-area-weighted, present for all 32 rows (CT + AK). Appropriate for
  land-use/land-area allocation (e.g. `rpa-landuse-2030`'s consumption via
  `crosswalks/landuse2030_fips.py`).
- `population_weight_basis` / `population_share_of_predecessor` /
  `population_share_of_new_region` -- population-weighted, present **only**
  for CT's 19 `CT_2022_planning_regions` rows (empty string / `None` for the
  13 AK rows). Appropriate for demographic/economic allocation (e.g.
  `rpa-socioeconomic-downscaling`'s population/income panel).

Both share sets independently sum to 1.0 per predecessor and per successor
(validated in `tests/test_splits.py`). Neither is more "canonical" than the
other -- `Split.share_of_predecessor` never silently changed meaning; a new,
separate field was added instead, specifically so an existing consumer
reading the area columns (`landuse2030_fips.py`) wouldn't have its
methodology altered by a change made for a different consumer's needs.

CT's population weights use the same CT-Data-Collaborative town-level
crosswalk as the area weights, reweighted by each town's 2020 Census total
population (P.L. 94-171 Redistricting File, `POP100` field). That file is
downloaded unauthenticated from `www2.census.gov`'s bulk data mirror (not
the `api.census.gov` REST API, which does still require a key per the note
below) -- so no `CENSUS_API_KEY` was needed for this after all.

AK's six splits remain **area-only, deliberately deferred**: unlike CT's
town-level crosswalk (built for a *current*, static set of towns), AK's
predecessors are retired Census Areas -- apportioning their population would
require town/place-level 2020 population spatially joined against the
*historical* boundary, not just today's successor boundaries. That's
meaningfully harder and no downstream consumer has asked for it, so it's
left undone and documented (see each AK row's `note`) rather than guessed.

Historical note: `api.census.gov`, the Census Bureau's REST API, now
rejects unauthenticated requests and requires a key (`CENSUS_API_KEY` env
var, never hardcoded, if a future case needs it). That's a separate system
from the bulk `www2.census.gov` file downloads used here.

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

## Per-repo crosswalks (`src/rpa_geo/crosswalks/`)

Part of the installable `rpa_geo` package (moved here from a repo-root
`crosswalks/` directory so a consuming repo's `uv add --editable ../rpa-geo`
can actually import them, not just this repo's own test suite via a
`sys.path` hack).

| Repo | Key | Module | Status |
|---|---|---|---|
| rpa-socioeconomic-downscaling | `cid2` | `rpa_geo.crosswalks.downscaling_cid2` | All 3,197 live values resolve to an explicit status; 2 flagged for owner review (see findings below). Ships `validate_universe()`. |
| rpa-slr / rpa-slr-landuse | `county_fips` | `rpa_geo.crosswalks.slr_county_fips` | Pure identity mapping -- TIGER 2024 and canonical 2025 share an identical GEOID universe, verified by full diff. Ships `validate_universe()`. |
| rpa-landuse-2030 | `fips` | `rpa_geo.crosswalks.landuse2030_fips` | All 3,075 live `georef.csv` values resolve; 2 of the 3 anomalies found have been fixed upstream, 1 still open (see findings below). Ships `validate_universe()`. |
| rpa-data-portal | n/a | `rpa_geo.crosswalks.data_portal_landuse` | Documentation only, no resolve() (and so no `validate_universe()`) -- the ETL only ever aggregates to state (`county[:2]`), never publishes a county-level GEOID itself, so old/new CT is a non-issue there today. Source JSON wasn't available locally to validate further. |
| urban-rents / rpa-slr / rpa-slr-landuse outputs -> J. Prestemon's Stata models | canonical GEOID -> `cid2` | `rpa_geo.crosswalks.census2015` | The canonical 2025 <-> 2015-scheme link (see the dedicated section below). All but 37 canonical GEOIDs resolve; the 33 `membership_2015_unknown` codes and MP's 4 municipalities are documented gaps awaiting owner input. Ships `validate_universe()`. |

## The canonical 2025 <-> 2015 link (`crosswalks/census2015`)

The per-repo crosswalks above answer "what canonical geography does this
repo's key mean?". `census2015.py` answers the *opposite*, portfolio-level
question: **which location in the 2015-vintage scheme used by J. Prestemon's
Stata econometric models consumes this current county's value** -- the
direction needed to feed urban-rents / rpa-slr / rpa-slr-landuse outputs
(all keyed on current GEOIDs) into those models.

The 2015 side is the same scheme rpa-socioeconomic-downscaling carries as
`cid2`: approximately Census 2015 FIPS, plus BEA-style combination codes
(VA's 24 county+city combos, Maui 15901, Shawano/Menominee 55901) and two
structural divergences defined authoritatively by the owner's two final
crosswalk files (received 2026-07-16, archived at `~/Data/projects/rpa-geo/`,
converted to `census2015_link.csv` + `locations_2015_ak.csv`):

- **Alaska** (`Alaska_locations_final.xlsx`): 24 constant-geography
  locations that exactly partition the 30 current AK county-equivalents --
  17 unchanged codes, 2 retained legacy codes (02270 Wade Hampton/Kusilvak,
  02201 Prince of Wales), and 5 aggregates (02231 = Skagway+Yakutat+
  Hoonah-Angoon; 02261, 02280; and 02070/02290, which *include* Lake and
  Peninsula/Denali even though those codes are also current GEOIDs). Also
  carries the owner's per-location `coastal` flag (`ak_locations()`).
- **Connecticut** (`ct_cou_to_cousub_crosswalk_final_choices.xlsx`, sheet
  `Final_Assignment_for_Urban_Rent`): each old county reads exactly ONE
  current planning region -- Capitol (09110) is read by both Hartford and
  Tolland, South Central (09170) and Western (09190) are deliberately read
  by nobody, and Fairfield/New Haven are assigned *against* the
  largest-share region (09120/09140, not 09190/09170). This is the owner's
  final 1:1 choice for connecting model data flows; it lives **alongside**
  the weighted many-to-many CT allocation in `historical_splits.csv`, which
  remains the right tool for *allocating* data across the boundary change
  and is unchanged.

```python
from rpa_geo.crosswalks.census2015 import resolve, from_2015, validate_universe

resolve("02164").geoids_2015   # ("02070",) -- aggregate into Dillingham+L&P
resolve("09110").geoids_2015   # ("09003", "09013") -- replicate to both
from_2015("02231").geoids_2025 # ("02105", "02230", "02282") -- members to aggregate
validate_universe(county_geoids_of_an_output)  # fail loud on the 37 documented gaps
```

**Known gaps, flagged not guessed** (`membership_2015_unknown`, 33 codes):
28 VA independent cities, Kalawao HI, Shawano WI, La Paz AZ, Cibola NM, and
Broomfield CO have no code of their own in the live `cid2` universe and are
presumably absorbed into a neighboring combination code (BEA's definitions
suggest where) -- but no owner-provided file confirms the membership, so
`resolve()` flags them and `validate_universe()` raises. Closing this needs
a third crosswalk file (or explicit confirmation) from the owner --
consequential for rpa-slr flows especially, since several of the flagged VA
cities are coastal (e.g. Poquoson 51735, Williamsburg 51830; the larger
Hampton Roads cities like Norfolk have their own codes in the scheme and
resolve fine). Northern Mariana Islands' 4 municipalities are similarly
`territory_unmodeled` (no owner decision recorded, unlike American Samoa's
documented exclusion).

## Enforcing the contract: `validate_universe()`

A crosswalk's `resolve()` only tells you the answer for one key at a time --
nothing stops a consuming repo's pipeline from calling it, getting an
`unresolved_needs_review` status back, and quietly proceeding anyway (this
is exactly the shape of a real bug found in `rpa-landuse-2030`'s
`slr_mask.py`: a county-key mismatch there silently returns zero candidate
plots, indistinguishable from "this county legitimately has none"). A test
that checks this once isn't enough either -- it only covers whatever
universe of keys existed when the test was written, not whatever shows up
in production data next year.

`validate_universe()` is the fail-loud version, meant to be called at a
repo's own data-ingest boundary, in the pipeline's actual code path:

```python
from rpa_geo.crosswalks.downscaling_cid2 import validate_universe

# Raises pandera.errors.SchemaErrors -- listing every offending key and the
# category it resolved to, not just the first -- if anything falls outside
# the allowed set. Call this where the pipeline currently trusts its county
# key blindly, not just in a test.
validate_universe(live_cid2_values)
```

Every crosswalk with a `resolve()` (all but `data_portal_landuse`, which has
none) ships one. Internally, each fine-grained `Status` (e.g.
`ct_allocation`, `ak_split_allocation`, `pacific_1to1`) maps to one of seven
shared `Category` values via `rpa_geo.contracts.STATUS_CATEGORY` --
`direct`, `history_edge`, `split_allocation`, `territory_fanout`,
`out_of_scope`, `inert_placeholder`, `unresolved_needs_review`. This exists
because two crosswalks independently hand-rolled near-identical
allocation/out-of-scope logic under different names; the shared `Category`
stops a third one from doing it again, without renaming any existing
`Status` string (nothing outside this package depends on those strings yet,
but the crosswalks' own tests do, so nothing was renamed to avoid an
unnecessary breaking change).

By default, `validate_universe()` allows anything that's fully resolved or
correctly, knowingly excluded (`direct`, `history_edge`,
`split_allocation`, `out_of_scope`, `inert_placeholder` --
`rpa_geo.contracts.RESOLVED_CATEGORIES`) and raises on anything that
represents a genuine live gap (`territory_fanout`, `unresolved_needs_review`
-- no live cid2 lands in either today, after the `02231` / American Samoa
resolutions below). A caller who's consciously
decided to tolerate a specific gap can widen the allowed set explicitly via
the `allow=` argument -- the default just doesn't make that choice silently.

## Nonstandard county-equivalents

`rpa_geo.nonstandard_county_equivalents()` is a documented, tested set of
GEOIDs whose real-world shape -- independent city, consolidated
city-county government, or the federal district -- commonly breaks code
that assumes every place nests under exactly one ordinary "county" parent.
Three different repos (and this package's own crosswalks) have separately
rediscovered pieces of this; this is meant to let the *next* one self-check
before shipping instead of rediscovering it again the way
`rpa-landuse-2030` issue #87 did.

It's a union of two parts, verified by direct inspection of
`counties_2025.csv` (not assumed from Census documentation alone):

- **Mechanically derived**: every GEOID with Census `lsad` code `"25"`
  ("city (independent)") -- Baltimore MD, St. Louis MO, and all of
  Virginia's independent cities. This updates itself automatically if a
  future vintage adds or removes one; no maintenance needed.
- **Hand-curated** (`CONSOLIDATED_CITY_COUNTY_GEOIDS`): Denver and
  Broomfield, CO, Carson City, NV, and DC. None of these are distinguishable
  from an ordinary county by any single field in the source extract --
  Denver and Broomfield share the ordinary county `lsad` "06" with ~3,000
  unrelated rows; DC shares `lsad` "00" with unrelated territory
  placeholders (Guam, two uninhabited American Samoa islands). Cited here
  the same way `history_edges.csv` cites entries that can't be mechanically
  derived either.

This is **not** a completeness check. A GEOID can be a perfectly ordinary
county (Arlington, VA, `lsad` "06") and still be missing from some other
repo's own reference table for a completely unrelated reason -- that's what
`rpa-landuse-2030`'s `KNOWN_MISSING_CONUS_GEOIDS` (in
`crosswalks/landuse2030_fips.py`) already checks separately, by diffing
against `load_counties()`'s `is_conus` flag. Use that kind of diff for
completeness; use this set to check whether your own ingestion code even
handles this *shape* of GEOID at all.

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
  even the 2007 Skagway-Hoonah-Angoon split. It was flagged
  `unresolved_needs_review`, then mapped 1:1 to Hoonah-Angoon (`02105`) per
  a 2026-07-13 owner instruction, then **superseded on 2026-07-16** by the
  owner's `Alaska_locations_final.xlsx`, which defines it as the full
  three-way Skagway+Yakutat+Hoonah-Angoon aggregate -- now an
  `AK_skagway_yakutat_angoon_1992` split in `historical_splits.csv` (the
  composition also matches the genuine Census history: Yakutat split off in
  1992, the remainder split again in 2007).
- **`cid2=02070` and `cid2=02290` are aggregates, not the current counties
  their codes match.** Discovered from `Alaska_locations_final.xlsx`
  (2026-07-16): the owner's 02070 is "Dillingham + Lake and Peninsula"
  (02164 seceded 1989) and his 02290 is "Yukon-Koyukuk + Denali" (02068
  incorporated 1990); both predecessor codes survive as current GEOIDs with
  smaller boundaries, so the previous `direct` treatment silently dropped
  Lake and Peninsula and Denali from his scheme. Now
  `historical_splits.csv` cases; `downscaling_cid2.resolve()` fans them out.
- **The live downscaling panel double-carries the AK aggregate members with
  inconsistent `dropthis` flags**: standalone series exist for 02105, 02164,
  02195, 02230, 02275, 02282 even though the owner's final location file
  carries those areas inside the 02070/02231/02280 aggregates -- and only
  02105/02195 are marked `dropthis=1` (02164/02230/02275/02282 are kept,
  which double-counts if summed with their aggregates). That repo's data,
  that owner's call -- pinned in `tests/test_census2015.py` so a change on
  their side shows up as a test diff here, and worth raising with him.
- **`cid2=55901` likely covers Shawano County too, not Menominee alone**:
  Shawano (55115) is absent from the live cid2 universe while 55901 is
  present, and BEA defines 55901 as "Shawano (incl. Menominee)". The
  `history_edges.csv` mapping (55901 -> 55078) is left unchanged pending
  owner confirmation; the note on that edge records the evidence, and the
  reverse direction flags 55115 as `membership_2015_unknown`.
- **`cid2=74001`** (American Samoa) carries the territory as a single row,
  though Census recognizes five districts (`60010`-`60050`). Rather than fan
  it out without weights, the downscaling owner elected not to model American
  Samoa (2026-07-13), so it's flagged `inert_placeholder` (knowingly
  excluded).
- **`cid2=02999`** ("REMAINDER OF ALASKA", `dropthis=1` and zero non-null
  population rows in the source panel) -- flagged `inert_placeholder`, not
  silently dropped.
- **rpa-landuse-2030's `georef.csv` represented part of Connecticut twice**
  (all 8 old counties *and* 2 of the 9 new planning regions, Lower
  Connecticut River Valley 09130 + Southeastern Connecticut 09180, as
  independent rows -- double-counting for anything summing every row without
  deduplicating CT). Flagged `ct_duplicate_direct`, reported upstream as
  issue #80. **Fixed 2026-07-10** in that repo's PR #86 (dropped at the
  source in `nri_extractor._create_georef_from_transitions()`) -- verified
  against the live file; `CT_DUPLICATE_NEW_REGIONS` is now an empty,
  documented frozenset in `crosswalks/landuse2030_fips.py` so a regression
  would be caught again automatically.
- **rpa-landuse-2030's `georef.csv` had 27 non-CONUS rows despite its own
  documented CONUS+DC-only design** (`NON_CONUS_STATEFP`): 4 of HI's 5
  counties, 22 of PR's 78 municipios, 1 of VI's 3 islands, zero AK/GU/AS/MP
  -- issue #81 speculated this leaked in via a BEA CAINC1 regional-accounts
  join (per the `raw/` directory's file names), a theory the fix below
  neither confirms nor rules out. Flagged `out_of_scope_but_present`,
  reported upstream as issue #81. **Fixed 2026-07-10** in the same PR #86
  (CONUS+DC filter added, reusing `geo.py`'s own `NON_CONUS_STATEFP`) --
  verified against the live file; `UNEXPECTED_NON_CONUS_IN_GEOREF` is now an
  empty, documented frozenset for the same regression-catching reason.
- **rpa-landuse-2030's `georef.csv` is missing 35 canonical CONUS+DC
  GEOIDs entirely** -- a differently-shaped anomaly the two fixes above
  didn't surface, since `resolve()` only ever classifies fips values
  *present* in the file, never notices one that's absent. Found by diffing
  the full canonical `is_conus` set against the live file: DC (`11001`);
  Denver + Broomfield, CO (consolidated city-and-county governments,
  `08031`/`08014`); St. Louis City, MO (independent of any county,
  `29510`); Arlington County + 30 of Virginia's independent cities. Likely
  a longstanding NRI survey-coverage gap for non-standard
  county-equivalents (not a PR #86 regression -- see the issue for the
  reasoning), reported upstream as issue #87. `KNOWN_MISSING_CONUS_GEOIDS`
  in `crosswalks/landuse2030_fips.py` documents the exact set; not yet
  fixed upstream.

## Onboarding a new repo

1. Load `counties_2025.csv` as your join target.
2. If your data uses any GEOID in `history_edges.csv`'s `legacy_geoid`
   column, join through it to canonical first.
3. If your data uses a GEOID in `historical_splits.csv`'s
   `predecessor_geoid` column (CT's old counties, or one of the six AK
   splits), **first check which vintage your data is on**: two predecessor
   codes (`02070`, `02290`) are *also* ordinary current GEOIDs -- on
   current-vintage data they must pass through directly, and only
   2015-scheme data (like downscaling's `cid2`) should fan them out. Then
   pick a weight basis: land area (`share_of_predecessor` /
   `share_of_new_region`, all 25 rows) or, for CT only, 2020 town population
   (`population_share_of_predecessor` / `population_share_of_new_region`,
   19 rows -- `None` for AK). Use population weights if you're allocating
   people/economic data; land-area weights if you're allocating land. Then
   decide whether you need a 1:1 approximation (pick the `successor_geoid`
   with the largest share *on your chosen basis* -- `resolve_predecessor()`'s
   own ordering is always by the area share, so sort the returned tuple
   yourself if you picked population) or a true split (fan out by share,
   depending on direction).
4. Check any GEOID you can't resolve against `out_of_scope.csv` before
   assuming it's a bug in this package.
5. Add a per-repo crosswalk under `src/rpa_geo/crosswalks/` in this repo
   (see `src/rpa_geo/crosswalks/downscaling_cid2.py` for the pattern) and a
   test that round-trips every county in your live dataset to exactly one
   canonical row. Flag anything you can't responsibly resolve rather than
   guessing -- see the AK findings above for what that looks like in
   practice. Add every fine-grained `Status` your crosswalk introduces to
   `rpa_geo.contracts.STATUS_CATEGORY` (a test enforces this -- see
   `tests/test_contracts.py`), and ship a `validate_universe()` wrapper (a
   few lines -- see any existing crosswalk) so consumers get the fail-loud
   contract, not just `resolve()`.

## Onboarding a new vintage

Distinct from onboarding a new *repo* above -- this is for whenever the
Census Bureau ships the next cartographic boundary file (TIGER-2031+, after
the 2030 Census).

1. Ingest the new vintage's attribute table (the generalized
   `cb_YYYY_us_county_500k` file, same source as `counties_2025.csv`) as
   `counties_YYYY.csv`, **alongside** the prior vintage file, not replacing
   it -- `load_counties()` and `available_vintages()` pick it up
   automatically from the filename; no code change needed for that part.
2. Cross-reference the Census Bureau's own published documentation of
   changes between the two vintages, rather than inferring changes from a
   numeric GEOID diff alone. This isn't optional caution -- it's exactly
   the discipline that caught the Shannon-to-Oglala-Lakota direction bug in
   the current data (see "A direction bug we caught" above): a naive
   higher/lower-number heuristic got the rename direction backwards, and
   only checking a primary source caught it.
3. Classify every GEOID-set delta: unchanged, renamed 1:1 (add to
   `history_edges.csv`), split 1:many (add to `historical_splits.csv`,
   picking a fresh weight basis from new source data -- don't carry over a
   prior split's ratio), or merged many:1. The merge shape needs no schema
   change: `historical_splits.csv`'s row-per-(predecessor, successor) shape
   already generalizes to it (multiple predecessor rows can already point
   at one successor) -- it's simply unexercised by any real case so far.
4. Extend, don't overwrite, `history_edges.csv` / `historical_splits.csv`
   with the new interval's edges, each citing its primary source the way
   every existing edge already does.
5. Cut a new rpa-geo release. The version bump signals the new vintage is
   available; the old vintage file and its tag remain resolvable for any
   consumer not ready to move (see "Vintages are shipped side-by-side"
   above).
6. Each consuming repo migrates to the new vintage on its own schedule,
   using the same crosswalk-authoring pattern as "Onboarding a new repo"
   above -- except now both sides of the crosswalk are canonical schemas
   with identical column names, which is mechanically simpler than any of
   today's repo-specific crosswalks (each of which bridges canonical
   against a genuinely different, repo-invented key).

Add as a dependency from a consuming repo with:

```bash
uv add --editable ../rpa-geo
```

Then use your repo's crosswalk directly:

```python
from rpa_geo.crosswalks.downscaling_cid2 import resolve, validate_universe

r = resolve("09001")  # old Hartford County, CT
r.status            # "ct_allocation"
r.canonical_geoids  # the new planning-region GEOIDs it splits across
r.shares            # land-area weight per successor

# Fail loud at your own pipeline's ingest boundary, on the live universe --
# raises pandera.errors.SchemaErrors listing every offending key if
# anything falls outside the resolved/correctly-excluded categories.
validate_universe(live_cid2_values)
```
