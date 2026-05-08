from __future__ import annotations

import pytest

from atlas.domain import (
    CellInductionConflict,
    CellRegistered,
    CellStatusChanged,
    RegisterCell,
    Registry,
    SetCellStatus,
)
from tests.fixtures import FakeClock, InMemoryRepository


def make_registry() -> Registry:
    return Registry(repository=InMemoryRepository(), now_factory=FakeClock().now)


# ---------- register_cell ----------


def test_register_cell_creates_new_cell():
    registry = make_registry()
    [event] = registry.handle(
        RegisterCell(name="cytometer", purpose="cell counts", repo_url="git@x:c.git")
    )
    assert isinstance(event, CellRegistered)
    assert event.was_existing is False
    assert event.cell.name == "cytometer"
    assert event.cell.purpose == "cell counts"
    assert event.cell.repo_url == "git@x:c.git"
    assert event.cell.status == "active"
    assert event.cell.induced_by is None
    assert event.cell.id.startswith("cell_")
    assert event.cell.registered_at != ""


def test_register_cell_repo_url_is_optional():
    registry = make_registry()
    [event] = registry.handle(RegisterCell(name="cytometer", purpose="cell counts"))
    assert isinstance(event, CellRegistered)
    assert event.cell.repo_url is None


def test_register_cell_is_idempotent_on_name():
    registry = make_registry()
    [first] = registry.handle(RegisterCell(name="cytometer", purpose="cell counts"))
    [second] = registry.handle(
        RegisterCell(name="cytometer", purpose="different purpose, ignored")
    )
    assert isinstance(first, CellRegistered)
    assert isinstance(second, CellRegistered)
    assert second.was_existing is True
    assert second.cell.id == first.cell.id
    # The original purpose / fields are preserved — re-registering does
    # not overwrite existing state.
    assert second.cell.purpose == "cell counts"


def test_register_cell_with_induced_by_records_lineage():
    registry = make_registry()
    [event] = registry.handle(
        RegisterCell(name="growthplate", purpose="x", induced_by="morph_42")
    )
    assert isinstance(event, CellRegistered)
    assert event.cell.induced_by == "morph_42"


def test_register_cell_collides_on_existing_induced_by():
    registry = make_registry()
    [first] = registry.handle(
        RegisterCell(name="growthplate", purpose="x", induced_by="morph_42")
    )
    assert isinstance(first, CellRegistered)
    [second] = registry.handle(
        RegisterCell(name="rival_spawn", purpose="y", induced_by="morph_42")
    )
    assert isinstance(second, CellInductionConflict)
    assert second.attempted_name == "rival_spawn"
    assert second.induced_by == "morph_42"
    assert second.existing_cell.id == first.cell.id
    assert second.existing_cell.name == "growthplate"


def test_register_cell_idempotency_takes_precedence_over_induced_by_check():
    """Re-registering the *same* cell (same name) with the same induced_by
    is the idempotent path — not a collision."""
    registry = make_registry()
    [first] = registry.handle(
        RegisterCell(name="growthplate", purpose="x", induced_by="morph_42")
    )
    [second] = registry.handle(
        RegisterCell(name="growthplate", purpose="x", induced_by="morph_42")
    )
    assert isinstance(first, CellRegistered)
    assert isinstance(second, CellRegistered)
    assert second.was_existing is True
    assert second.cell.id == first.cell.id


def test_register_cell_allows_distinct_induced_by_values():
    registry = make_registry()
    [a] = registry.handle(
        RegisterCell(name="cell_a", purpose="x", induced_by="morph_1")
    )
    [b] = registry.handle(
        RegisterCell(name="cell_b", purpose="y", induced_by="morph_2")
    )
    assert isinstance(a, CellRegistered)
    assert isinstance(b, CellRegistered)
    assert a.cell.id != b.cell.id
    assert a.cell.induced_by == "morph_1"
    assert b.cell.induced_by == "morph_2"


def test_register_cell_does_not_check_induced_by_when_unset():
    """Two cells with induced_by=None should not collide with each other."""
    registry = make_registry()
    [a] = registry.handle(RegisterCell(name="cell_a", purpose="x"))
    [b] = registry.handle(RegisterCell(name="cell_b", purpose="y"))
    assert isinstance(a, CellRegistered)
    assert isinstance(b, CellRegistered)
    assert a.cell.id != b.cell.id


# ---------- set_cell_status ----------


def test_set_cell_status_active_to_inactive():
    registry = make_registry()
    [registered] = registry.handle(RegisterCell(name="c", purpose="p"))
    assert isinstance(registered, CellRegistered)
    [event] = registry.handle(
        SetCellStatus(cell_id=registered.cell.id, status="inactive")
    )
    assert isinstance(event, CellStatusChanged)
    assert event.cell.status == "inactive"
    assert event.cell.id == registered.cell.id


def test_set_cell_status_inactive_to_active():
    registry = make_registry()
    [registered] = registry.handle(RegisterCell(name="c", purpose="p"))
    assert isinstance(registered, CellRegistered)
    registry.handle(SetCellStatus(cell_id=registered.cell.id, status="inactive"))
    [event] = registry.handle(
        SetCellStatus(cell_id=registered.cell.id, status="active")
    )
    assert isinstance(event, CellStatusChanged)
    assert event.cell.status == "active"


def test_set_cell_status_is_no_op_when_already_at_status():
    registry = make_registry()
    [registered] = registry.handle(RegisterCell(name="c", purpose="p"))
    assert isinstance(registered, CellRegistered)
    [event] = registry.handle(
        SetCellStatus(cell_id=registered.cell.id, status="active")
    )
    assert isinstance(event, CellStatusChanged)
    assert event.cell.status == "active"


def test_set_cell_status_rejects_unknown_status():
    registry = make_registry()
    [registered] = registry.handle(RegisterCell(name="c", purpose="p"))
    assert isinstance(registered, CellRegistered)
    with pytest.raises(ValueError, match="Invalid cell status"):
        registry.handle(SetCellStatus(cell_id=registered.cell.id, status="pending"))


def test_set_cell_status_raises_for_unknown_cell():
    registry = make_registry()
    with pytest.raises(KeyError, match="Unknown cell"):
        registry.handle(SetCellStatus(cell_id="cell_missing", status="inactive"))


# ---------- get_cell / list_cells ----------


def test_get_cell_returns_cell_when_present():
    registry = make_registry()
    [registered] = registry.handle(RegisterCell(name="c", purpose="p"))
    assert isinstance(registered, CellRegistered)
    fetched = registry.get_cell(registered.cell.id)
    assert fetched is not None
    assert fetched.id == registered.cell.id
    assert fetched.name == "c"


def test_get_cell_returns_none_for_unknown_id():
    registry = make_registry()
    assert registry.get_cell("cell_missing") is None


def test_list_cells_returns_all_when_unfiltered():
    registry = make_registry()
    registry.handle(RegisterCell(name="a", purpose="x"))
    registry.handle(RegisterCell(name="b", purpose="y"))
    cells = registry.list_cells()
    assert {cell.name for cell in cells} == {"a", "b"}


def test_list_cells_filters_by_status():
    registry = make_registry()
    [reg_a] = registry.handle(RegisterCell(name="a", purpose="x"))
    [reg_b] = registry.handle(RegisterCell(name="b", purpose="y"))
    assert isinstance(reg_a, CellRegistered)
    assert isinstance(reg_b, CellRegistered)
    registry.handle(SetCellStatus(cell_id=reg_b.cell.id, status="inactive"))

    actives = registry.list_cells(status="active")
    inactives = registry.list_cells(status="inactive")
    assert {cell.name for cell in actives} == {"a"}
    assert {cell.name for cell in inactives} == {"b"}


# ---------- handle() dispatch ----------


def test_handle_rejects_unknown_command():
    registry = make_registry()

    class Bogus:
        pass

    with pytest.raises(TypeError, match="Unknown command"):
        registry.handle(Bogus())
