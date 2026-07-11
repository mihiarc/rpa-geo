"""County-identity notes for rpa-data-portal's land-base ETL.

Unlike the other three crosswalks in this repo, this is *not* a resolve()
function backed by a live county-level dataset -- rpa-data-portal's
``land-base/main.py`` never publishes or re-reads a county-level GEOID
itself. It reads the RDS-2023-0026 source JSON's per-county 6x6 land-use
transition tables and immediately aggregates them to state via
``state = county[:2]`` (main.py line 124), then rolls state up to region/
nation. Published output (``public/data/land-base/*.json``) only has
nation/region/state geographies -- confirmed via ``index.json``'s
``geographies`` key, which lists no ``county`` entry.

Why this repo doesn't need a resolve() function today: state-level
aggregation by 2-digit FIPS prefix is insensitive to *which* Connecticut
county scheme (old 8 counties, 09001-09015, vs new 9 planning regions,
09110-09190) the source JSON uses -- both share the "09" prefix, so the
state total is identical either way. This repo's own ETL also already
fails loud on any unrecognized state prefix (main.py line 239:
``sys.exit(f"county FIPS prefix {state!r} is not a known state")``), so a
non-CONUS or malformed county code can't silently corrupt a state total.

RDS-2023-0026 (Mihiar, Lewis & Coulston 2023) is the same underlying
land-use-projection source landuse_rpa_2030 is built on (see that repo's
``columns.py`` module docstring) -- if this ETL ever grows a county-level
view, adopt rpa-geo's canonical table directly rather than inventing a new
scheme, and expect the same CT old8/new9 question
``crosswalks/landuse2030_fips.py`` already resolves. The source JSON itself
wasn't available in this checkout (gitignored raw data) to validate
directly; this module documents the finding rather than a resolve() table
so it isn't presented as more verified than it is.
"""
