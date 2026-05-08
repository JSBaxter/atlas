"""Invariants on the public model surface.

These are deliberately thin — the models are pure data containers with
no behavior, so the registry tests cover most of the meaningful ground.
What lives here is the shape contract that downstream PRs (sqlite repo,
MCP server) and other cells (morphogen) read from and depend on.
"""

from atlas.domain.models import CELL_STATUSES, TAG_STATUSES


def test_cell_status_set_is_active_or_inactive():
    assert CELL_STATUSES == frozenset({"active", "inactive"})


def test_tag_status_set_is_active_or_deprecated():
    assert TAG_STATUSES == frozenset({"active", "deprecated"})
