import rpa_geo
from crosswalks import data_portal_landuse


def test_module_documents_why_no_resolve_function():
    assert data_portal_landuse.__doc__ is not None
    assert "state = county[:2]" in data_portal_landuse.__doc__


def test_state_prefix_aggregation_is_ct_scheme_agnostic():
    """The premise data_portal_landuse.py relies on: old and new CT GEOIDs
    share the same 2-digit state prefix, so main.py's `county[:2]`
    aggregation gives the same state total regardless of which CT county
    scheme the source JSON happens to use."""
    old_ct = "09001"
    new_ct = "09190"
    assert old_ct[:2] == new_ct[:2] == "09"

    counties = rpa_geo.load_counties()
    assert new_ct in counties
    assert (
        old_ct not in counties
    )  # confirms this really is an old/retired code, not a live alternative
