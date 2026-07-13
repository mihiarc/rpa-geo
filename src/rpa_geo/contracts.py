"""Shared resolution-status vocabulary and the executable validation contract.

``downscaling_cid2.py`` and ``landuse2030_fips.py`` were built independently
and each hand-rolled its own ``Status`` literal for the same underlying
shapes (a Connecticut-style reorganization and an Alaska-style Census Area
split are mechanically identical -- an allocation across several successor
GEOIDs with weights -- but the two crosswalks named them ``ct_allocation``
and ``ak_split_allocation`` with no shared type between them). This module
promotes that latent vocabulary to a first-class ``Category``, and provides
one fail-loud validation entrypoint every crosswalk's ``validate_universe()``
wraps, instead of four independent almost-duplicates.

Per-crosswalk ``Status`` literals are kept as-is (not renamed) -- they carry
real distinctions a coarser category collapses (e.g. *which* allocation
weight basis applies), and nothing outside this package depends on the
category names yet, so there's no cost to keeping both. See README.md's
"Enforcing the contract" section for how a consuming repo is expected to
call ``validate_universe()``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Literal, Protocol

import pandera.pandas as pa
import pandas as pd

Category = Literal[
    "direct",  # already the canonical GEOID
    "history_edge",  # 1:1 legacy code
    "split_allocation",  # one predecessor -> several successors, with weights (CT- or AK-style)
    "territory_fanout",  # a Pacific placeholder that can't collapse to one GEOID, no weights yet
    "out_of_scope",  # correctly recognized as not real Census geography
    "inert_placeholder",  # correctly recognized as an unused/empty code, safe to ignore
    "unresolved_needs_review",  # a genuine gap, or an anomaly contradicting the repo's own design
]

# Categories a repo can treat as "cleanly handled" without a human in the
# loop -- everything here is either fully resolved (direct/history_edge/
# split_allocation) or correctly and knowingly excluded (out_of_scope/
# inert_placeholder). territory_fanout and unresolved_needs_review are live
# gaps -- no weights exist yet, or resolve() genuinely doesn't know -- and
# are deliberately left out of this default.
RESOLVED_CATEGORIES: frozenset[Category] = frozenset(
    {
        "direct",
        "history_edge",
        "split_allocation",
        "out_of_scope",
        "inert_placeholder",
    }
)

# Every fine-grained Status string used by any crosswalk in this package,
# mapped to its shared Category. Add an entry here whenever a crosswalk
# introduces a new Status -- category() raises on anything missing rather
# than guessing, the same "don't silently drop" discipline the crosswalks
# themselves follow.
STATUS_CATEGORY: dict[str, Category] = {
    # shared across downscaling_cid2 / landuse2030_fips / slr_county_fips
    "direct": "direct",
    "history_edge": "history_edge",
    "unresolved": "unresolved_needs_review",
    # downscaling_cid2-specific
    "ct_allocation": "split_allocation",
    "ak_split_allocation": "split_allocation",
    "pacific_1to1": "direct",  # Guam: a placeholder code, but a clean 1:1 resolution
    "pacific_unresolved": "territory_fanout",
    "out_of_scope": "out_of_scope",
    "inert_placeholder": "inert_placeholder",
    "unresolved_needs_review": "unresolved_needs_review",
    # landuse2030_fips-specific
    "ct_duplicate_direct": "unresolved_needs_review",  # double-count risk, needs a human despite the name
    "out_of_scope_by_design": "out_of_scope",
    "out_of_scope_but_present": "unresolved_needs_review",  # contradicts the repo's own design
}


def category(status: str) -> Category:
    """The shared Category for a crosswalk-specific Status string."""
    try:
        return STATUS_CATEGORY[status]
    except KeyError as exc:
        raise KeyError(
            f"Status {status!r} has no registered Category -- add it to "
            "rpa_geo.contracts.STATUS_CATEGORY when a crosswalk introduces a "
            "new status."
        ) from exc


class _HasStatus(Protocol):
    @property
    def status(self) -> str: ...


def validate_universe(
    keys: Iterable[str],
    resolve: Callable[[str], _HasStatus],
    *,
    allow: frozenset[Category] = RESOLVED_CATEGORIES,
) -> None:
    """Resolve every key and fail loud if any lands outside ``allow``.

    This is the runtime half of the contract: a repo calls this at its own
    data-ingest boundary (where it currently trusts its county key blindly),
    not in a skippable test. Raises ``pandera.errors.SchemaErrors`` listing
    every offending key and the category it resolved to -- not just the
    first one -- if anything falls outside ``allow``.

    Deliberately generic over ``resolve`` rather than one copy per crosswalk:
    every crosswalk in this package already exposes a ``resolve(key) ->
    Resolution`` with a ``.status`` attribute, so this is the one place the
    Pandera plumbing lives.
    """
    keys = list(keys)
    resolved_categories = pd.Series(
        [category(resolve(k).status) for k in keys], index=keys, name="category"
    )
    schema = pa.SeriesSchema(
        str,
        checks=pa.Check(
            lambda c: c in allow,
            element_wise=True,
            error=f"resolved to a category outside the allowed set {sorted(allow)}",
        ),
        name="category",
    )
    schema.validate(resolved_categories, lazy=True)
