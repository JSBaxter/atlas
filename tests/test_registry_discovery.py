from __future__ import annotations

from dataclasses import replace

import pytest

from atlas.domain import (
    CapabilityBinding,
    CapabilityDeclared,
    Cell,
    CellRegistered,
    DeclareCapability,
    DeprecateTag,
    RegisterCell,
    Registry,
    RevokeCapability,
    SetCellStatus,
    StaleBindingsReport,
)
from tests.fixtures import FakeClock, InMemoryRepository


def make_registry() -> tuple[Registry, InMemoryRepository]:
    repo = InMemoryRepository()
    return Registry(repository=repo, now_factory=FakeClock().now), repo


def register_cell(
    registry: Registry, name: str, *, induced_by: str | None = None
) -> Cell:
    [event] = registry.handle(
        RegisterCell(name=name, purpose="x", induced_by=induced_by)
    )
    assert isinstance(event, CellRegistered)
    return event.cell


def declare(
    registry: Registry,
    cell_id: str,
    tag: str,
    description: str | None = "x",
) -> CapabilityBinding:
    [event] = registry.handle(
        DeclareCapability(cell_id=cell_id, tag=tag, description=description)
    )
    assert isinstance(event, CapabilityDeclared)
    return event.binding


def make_binding_stale(
    repo: InMemoryRepository, cell_id: str, tag: str, *, days_old: int = 30
) -> None:
    """Backdate a binding's last_refreshed_at by ``days_old`` days
    (well past the 14-day staleness threshold)."""
    binding = repo.get_capability_binding(cell_id, tag)
    assert binding is not None
    repo.update_capability_binding(
        replace(
            binding, last_refreshed_at=f"2026-04-{30 - days_old:02d}T00:00:00+00:00"
        )
    )


# ---------- find_capable ----------


def test_find_capable_with_empty_tags_returns_empty():
    registry, _ = make_registry()
    assert registry.find_capable(tags=[]) == []


def test_find_capable_with_invalid_mode_raises():
    registry, _ = make_registry()
    with pytest.raises(ValueError, match="Invalid mode"):
        registry.find_capable(tags=["t"], mode="some")


def test_find_capable_returns_cells_with_exact_tag_match():
    registry, _ = make_registry()
    cell_a = register_cell(registry, "cell_a")
    cell_b = register_cell(registry, "cell_b")
    declare(registry, cell_a.id, "t")
    declare(registry, cell_b.id, "other")
    cells = registry.find_capable(tags=["t"])
    assert [c.name for c in cells] == ["cell_a"]


def test_find_capable_excludes_inactive_cells():
    registry, _ = make_registry()
    cell = register_cell(registry, "c")
    declare(registry, cell.id, "t")
    registry.handle(SetCellStatus(cell_id=cell.id, status="inactive"))
    assert registry.find_capable(tags=["t"]) == []


def test_find_capable_excludes_stale_bindings():
    registry, repo = make_registry()
    cell = register_cell(registry, "c")
    declare(registry, cell.id, "t")
    make_binding_stale(repo, cell.id, "t")
    assert registry.find_capable(tags=["t"]) == []


def test_find_capable_returns_unknown_tag_as_empty():
    registry, _ = make_registry()
    cell = register_cell(registry, "c")
    declare(registry, cell.id, "t")
    assert registry.find_capable(tags=["never-declared"]) == []


def test_find_capable_returns_cells_sorted_by_name():
    registry, _ = make_registry()
    cell_z = register_cell(registry, "z")
    cell_a = register_cell(registry, "a")
    cell_m = register_cell(registry, "m")
    for cell in (cell_z, cell_a, cell_m):
        declare(registry, cell.id, "t")
    cells = registry.find_capable(tags=["t"])
    assert [c.name for c in cells] == ["a", "m", "z"]


def test_find_capable_deduplicates_when_cell_has_multiple_matching_bindings():
    """A single cell with bindings to both an ancestor and a descendant
    of the query tag should only appear once in the result."""
    registry, _ = make_registry()
    cell = register_cell(registry, "c")
    declare(registry, cell.id, "analysis")
    declare(registry, cell.id, "analysis.static")
    cells = registry.find_capable(tags=["analysis"])
    assert [c.name for c in cells] == ["c"]


# ---------- prefix matching ----------


def test_find_capable_matches_descendants_of_query_tag():
    """Querying 'analysis' should match a cell bound to
    'analysis.static.python' (descendant in the dot hierarchy)."""
    registry, _ = make_registry()
    cell = register_cell(registry, "c")
    declare(registry, cell.id, "analysis.static.python")
    cells = registry.find_capable(tags=["analysis"])
    assert [c.name for c in cells] == ["c"]


def test_find_capable_matches_ancestors_of_query_tag():
    """Querying 'analysis.static.python' should match a cell bound to
    'analysis' (ancestor in the dot hierarchy)."""
    registry, _ = make_registry()
    cell = register_cell(registry, "c")
    declare(registry, cell.id, "analysis")
    cells = registry.find_capable(tags=["analysis.static.python"])
    assert [c.name for c in cells] == ["c"]


def test_find_capable_does_not_match_unrelated_tags_with_shared_substring():
    """'analysis.static' is NOT in the dot hierarchy of 'analytics', even
    though they share a string prefix. Match must respect the dot
    boundary."""
    registry, _ = make_registry()
    cell = register_cell(registry, "c")
    declare(registry, cell.id, "analytics")
    assert registry.find_capable(tags=["analysis"]) == []


# ---------- alias resolution ----------


def test_find_capable_resolves_alias_forward():
    """Querying a deprecated tag should match cells bound to its
    canonical replacement."""
    registry, _ = make_registry()
    cell = register_cell(registry, "c")
    declare(registry, cell.id, "static-analysis")
    declare(registry, cell.id, "sast")
    registry.handle(DeprecateTag(tag="sast", alias_to="static-analysis"))
    # Query "sast" — the deprecated alias — should still find the cell
    # via its binding to either "sast" or "static-analysis".
    cells = registry.find_capable(tags=["sast"])
    assert [c.name for c in cells] == ["c"]


def test_find_capable_resolves_alias_reverse():
    """Querying a canonical tag should match cells whose only binding is
    to a deprecated alias of it. The two names refer to the same
    capability."""
    registry, _ = make_registry()
    cell = register_cell(registry, "c")
    declare(registry, cell.id, "static-analysis")
    declare(registry, cell.id, "sast")
    registry.handle(DeprecateTag(tag="sast", alias_to="static-analysis"))
    # Now revoke the canonical binding to leave only the deprecated one.
    registry.handle(RevokeCapability(cell_id=cell.id, tag="static-analysis"))
    cells = registry.find_capable(tags=["static-analysis"])
    assert [c.name for c in cells] == ["c"]


def test_find_capable_combines_alias_with_prefix_match():
    """Querying canonical 'analysis' should match a cell bound to
    'static-analysis.python' when 'static-analysis' is aliased to
    'analysis' — alias resolution lifts the descendant under the
    canonical's hierarchy."""
    registry, _ = make_registry()
    cell = register_cell(registry, "c")
    declare(registry, cell.id, "analysis")
    declare(registry, cell.id, "static-analysis")
    declare(registry, cell.id, "static-analysis.python")
    registry.handle(DeprecateTag(tag="static-analysis", alias_to="analysis"))

    # Querying 'analysis' picks up the cell via static-analysis.python
    # (descendant of static-analysis, which aliases to analysis).
    cells = registry.find_capable(tags=["analysis"])
    assert [c.name for c in cells] == ["c"]


# ---------- mode all / any ----------


def test_find_capable_mode_all_intersects():
    registry, _ = make_registry()
    cell_both = register_cell(registry, "both")
    cell_one = register_cell(registry, "one")
    declare(registry, cell_both.id, "a")
    declare(registry, cell_both.id, "b")
    declare(registry, cell_one.id, "a")
    cells = registry.find_capable(tags=["a", "b"], mode="all")
    assert [c.name for c in cells] == ["both"]


def test_find_capable_mode_any_unions():
    registry, _ = make_registry()
    cell_a = register_cell(registry, "cell_a")
    cell_b = register_cell(registry, "cell_b")
    declare(registry, cell_a.id, "a")
    declare(registry, cell_b.id, "b")
    cells = registry.find_capable(tags=["a", "b"], mode="any")
    assert [c.name for c in cells] == ["cell_a", "cell_b"]


def test_find_capable_mode_all_returns_empty_when_no_cell_has_all():
    registry, _ = make_registry()
    cell_a = register_cell(registry, "cell_a")
    cell_b = register_cell(registry, "cell_b")
    declare(registry, cell_a.id, "a")
    declare(registry, cell_b.id, "b")
    assert registry.find_capable(tags=["a", "b"], mode="all") == []


# ---------- find_induced_by ----------


def test_find_induced_by_returns_matching_cell():
    registry, _ = make_registry()
    cell = register_cell(registry, "spawn", induced_by="morph_42")
    cells = registry.find_induced_by("morph_42")
    assert [c.id for c in cells] == [cell.id]


def test_find_induced_by_returns_empty_for_unknown_id():
    registry, _ = make_registry()
    register_cell(registry, "c", induced_by="morph_42")
    assert registry.find_induced_by("morph_99") == []


def test_find_induced_by_returns_empty_when_cell_has_no_induced_by():
    registry, _ = make_registry()
    register_cell(registry, "c")  # no induced_by
    assert registry.find_induced_by("morph_42") == []


# ---------- sweep_stale_capabilities ----------


def test_sweep_stale_capabilities_with_empty_repo():
    registry, _ = make_registry()
    report = registry.sweep_stale_capabilities()
    assert isinstance(report, StaleBindingsReport)
    assert report.threshold_days == 14
    assert report.stale_bindings == []


def test_sweep_stale_capabilities_with_only_fresh_bindings_returns_empty():
    registry, _ = make_registry()
    cell = register_cell(registry, "c")
    declare(registry, cell.id, "t")
    report = registry.sweep_stale_capabilities()
    assert report.stale_bindings == []


def test_sweep_stale_capabilities_returns_only_stale_bindings():
    registry, repo = make_registry()
    cell = register_cell(registry, "c")
    declare(registry, cell.id, "fresh-tag")
    declare(registry, cell.id, "stale-tag")
    make_binding_stale(repo, cell.id, "stale-tag")
    report = registry.sweep_stale_capabilities()
    assert {b.tag for b in report.stale_bindings} == {"stale-tag"}


def test_sweep_stale_capabilities_orders_by_cell_id_then_tag():
    registry, repo = make_registry()
    cell_a = register_cell(registry, "cell_a")
    cell_b = register_cell(registry, "cell_b")
    declare(registry, cell_a.id, "z")
    declare(registry, cell_a.id, "a")
    declare(registry, cell_b.id, "m")
    for cell, tag in [(cell_a, "z"), (cell_a, "a"), (cell_b, "m")]:
        make_binding_stale(repo, cell.id, tag)
    report = registry.sweep_stale_capabilities()
    keys = [(b.cell_id, b.tag) for b in report.stale_bindings]
    assert keys == sorted(keys)


def test_sweep_stale_capabilities_respects_threshold_days_parameter():
    """A 1-day threshold should mark recently-declared bindings stale
    when their timestamp is several days old. With the default 14-day
    threshold the same binding is fresh."""
    registry, repo = make_registry()
    cell = register_cell(registry, "c")
    declare(registry, cell.id, "t")
    # Backdate 5 days — fresh under 14d, stale under 1d.
    binding = repo.get_capability_binding(cell.id, "t")
    assert binding is not None
    repo.update_capability_binding(
        replace(binding, last_refreshed_at="2026-05-03T12:00:00+00:00")
    )
    assert registry.sweep_stale_capabilities(threshold_days=14).stale_bindings == []
    short_threshold_report = registry.sweep_stale_capabilities(threshold_days=1)
    assert {b.tag for b in short_threshold_report.stale_bindings} == {"t"}


def test_sweep_stale_capabilities_threshold_iso_is_consistent_with_days():
    """The reported threshold_iso should be (now - threshold_days)."""
    registry, _ = make_registry()
    report = registry.sweep_stale_capabilities(threshold_days=14)
    # FakeClock yields 2026-05-08T12:00:01+00:00 first; threshold is
    # 14 days earlier.
    assert report.threshold_iso.startswith("2026-04-24T")
