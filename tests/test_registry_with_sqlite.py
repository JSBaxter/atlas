"""Smoke tests proving the Registry works against the SQLite repository
identically to the in-memory fixture. Not a re-run of every test —
those live against InMemoryRepository for speed. This file is the
load-bearing proof that swapping the backend is a no-op."""

from __future__ import annotations

import sqlite3

from atlas.domain import (
    CapabilityDeclared,
    CellRegistered,
    DeclareCapability,
    DeprecateTag,
    RegisterCell,
    Registry,
)
from atlas.infra import SQLiteRepository
from tests.fixtures import FakeClock


def make_registry() -> Registry:
    connection = sqlite3.connect(":memory:")
    repository = SQLiteRepository(connection)
    repository.init_schema()
    return Registry(repository=repository, now_factory=FakeClock().now)


def test_registry_with_sqlite_round_trips_a_cell():
    registry = make_registry()
    [event] = registry.handle(RegisterCell(name="cytometer", purpose="x"))
    assert isinstance(event, CellRegistered)
    fetched = registry.get_cell(event.cell.id)
    assert fetched is not None
    assert fetched.name == "cytometer"


def test_registry_with_sqlite_persists_capability_binding_and_tag():
    registry = make_registry()
    [reg] = registry.handle(RegisterCell(name="c", purpose="p"))
    assert isinstance(reg, CellRegistered)
    [decl] = registry.handle(
        DeclareCapability(cell_id=reg.cell.id, tag="t", description="x")
    )
    assert isinstance(decl, CapabilityDeclared)
    assert decl.tag_was_new is True
    bindings = registry.list_capabilities(cell_id=reg.cell.id)
    assert [b.tag for b in bindings] == ["t"]


def test_registry_with_sqlite_find_capable_resolves_alias():
    """The full alias-resolution path works against SQLite — proves the
    repo's get_tag and list_tags wire correctly through the registry's
    discovery helpers."""
    registry = make_registry()
    [reg] = registry.handle(RegisterCell(name="c", purpose="p"))
    assert isinstance(reg, CellRegistered)
    registry.handle(
        DeclareCapability(cell_id=reg.cell.id, tag="static-analysis", description="x")
    )
    registry.handle(DeclareCapability(cell_id=reg.cell.id, tag="sast", description="y"))
    registry.handle(DeprecateTag(tag="sast", alias_to="static-analysis"))
    cells = registry.find_capable(tags=["sast"])
    assert [c.name for c in cells] == ["c"]


def test_registry_with_sqlite_induced_by_collision_caught_via_repo_or_service():
    """Either the Registry's pre-check or SQLite's UNIQUE INDEX must
    catch the spawn-race. Currently the Registry rejects with
    CellInductionConflict before the INSERT, so we don't see the
    IntegrityError — but verifying the conflict is reported is what
    matters for the contract."""
    from atlas.domain import CellInductionConflict

    registry = make_registry()
    [first] = registry.handle(
        RegisterCell(name="a", purpose="p", induced_by="morph_42")
    )
    assert isinstance(first, CellRegistered)
    [second] = registry.handle(
        RegisterCell(name="b", purpose="p", induced_by="morph_42")
    )
    assert isinstance(second, CellInductionConflict)
    assert second.existing_cell.name == "a"
