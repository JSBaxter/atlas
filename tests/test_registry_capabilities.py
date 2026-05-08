from __future__ import annotations

import pytest

from atlas.domain import (
    CapabilitiesRefreshed,
    CapabilityBinding,
    CapabilityDeclared,
    CapabilityRevoked,
    Cell,
    CellRegistered,
    DeclareCapability,
    RefreshCapabilities,
    RegisterCell,
    Registry,
    RevokeCapability,
)
from tests.fixtures import FakeClock, InMemoryRepository


def make_registry_with_cell(name: str = "cytometer") -> tuple[Registry, Cell]:
    registry = Registry(repository=InMemoryRepository(), now_factory=FakeClock().now)
    [event] = registry.handle(RegisterCell(name=name, purpose="x"))
    assert isinstance(event, CellRegistered)
    return registry, event.cell


# ---------- declare_capability ----------


def test_declare_capability_creates_binding_and_auto_registers_tag():
    registry, cell = make_registry_with_cell()
    [event] = registry.handle(
        DeclareCapability(
            cell_id=cell.id, tag="static-analysis", description="finds bugs"
        )
    )
    assert isinstance(event, CapabilityDeclared)
    assert event.tag_was_new is True
    assert event.tag.name == "static-analysis"
    assert event.tag.description == "finds bugs"
    assert event.tag.registered_by == cell.id
    assert event.tag.status == "active"
    assert event.binding.cell_id == cell.id
    assert event.binding.tag == "static-analysis"
    assert event.binding.declared_at != ""
    assert event.binding.last_refreshed_at == event.binding.declared_at
    assert event.suggestions == []


def test_declare_capability_against_existing_tag_skips_re_registration():
    registry, cell_a = make_registry_with_cell("cell_a")
    [decl_a] = registry.handle(
        DeclareCapability(cell_id=cell_a.id, tag="t", description="first")
    )
    assert isinstance(decl_a, CapabilityDeclared)
    [reg_b] = registry.handle(RegisterCell(name="cell_b", purpose="y"))
    assert isinstance(reg_b, CellRegistered)
    [decl_b] = registry.handle(
        DeclareCapability(cell_id=reg_b.cell.id, tag="t", description="ignored")
    )
    assert isinstance(decl_b, CapabilityDeclared)
    assert decl_b.tag_was_new is False
    # Tag carries the *original* description and registered_by, not the
    # second caller's.
    assert decl_b.tag.description == "first"
    assert decl_b.tag.registered_by == cell_a.id


def test_declare_capability_without_description_for_new_tag_raises():
    registry, cell = make_registry_with_cell()
    with pytest.raises(ValueError, match="description"):
        registry.handle(DeclareCapability(cell_id=cell.id, tag="brand-new"))


def test_declare_capability_without_description_for_existing_tag_is_ok():
    registry, cell = make_registry_with_cell()
    registry.handle(DeclareCapability(cell_id=cell.id, tag="t", description="first"))
    [reg_b] = registry.handle(RegisterCell(name="other", purpose="y"))
    assert isinstance(reg_b, CellRegistered)
    [event] = registry.handle(DeclareCapability(cell_id=reg_b.cell.id, tag="t"))
    assert isinstance(event, CapabilityDeclared)
    assert event.tag_was_new is False


def test_declare_capability_re_declare_refreshes_last_refreshed_at():
    registry, cell = make_registry_with_cell()
    [first] = registry.handle(
        DeclareCapability(cell_id=cell.id, tag="t", description="first")
    )
    [second] = registry.handle(DeclareCapability(cell_id=cell.id, tag="t"))
    assert isinstance(first, CapabilityDeclared)
    assert isinstance(second, CapabilityDeclared)
    assert second.binding.declared_at == first.binding.declared_at
    assert second.binding.last_refreshed_at > first.binding.last_refreshed_at


def test_declare_capability_unknown_cell_raises():
    registry = Registry(repository=InMemoryRepository(), now_factory=FakeClock().now)
    with pytest.raises(KeyError, match="Unknown cell"):
        registry.handle(
            DeclareCapability(cell_id="cell_missing", tag="t", description="x")
        )


# ---------- revoke_capability ----------


def test_revoke_capability_deletes_binding_and_signals_was_present():
    registry, cell = make_registry_with_cell()
    registry.handle(DeclareCapability(cell_id=cell.id, tag="t", description="x"))
    [event] = registry.handle(RevokeCapability(cell_id=cell.id, tag="t"))
    assert isinstance(event, CapabilityRevoked)
    assert event.was_present is True
    assert event.cell_id == cell.id
    assert event.tag == "t"
    assert registry.list_capabilities(cell_id=cell.id) == []


def test_revoke_capability_without_existing_binding_returns_was_present_false():
    registry, cell = make_registry_with_cell()
    [event] = registry.handle(RevokeCapability(cell_id=cell.id, tag="never-declared"))
    assert isinstance(event, CapabilityRevoked)
    assert event.was_present is False


def test_revoke_capability_unknown_cell_raises():
    registry = Registry(repository=InMemoryRepository(), now_factory=FakeClock().now)
    with pytest.raises(KeyError, match="Unknown cell"):
        registry.handle(RevokeCapability(cell_id="cell_missing", tag="t"))


def test_revoke_capability_does_not_remove_the_tag():
    """Revoke retracts a binding, not the tag itself. The tag survives
    so other cells can still declare it (or so deprecate_tag in PR 2c
    can act on it)."""
    registry, cell = make_registry_with_cell()
    registry.handle(DeclareCapability(cell_id=cell.id, tag="t", description="x"))
    registry.handle(RevokeCapability(cell_id=cell.id, tag="t"))
    [reg_b] = registry.handle(RegisterCell(name="other", purpose="y"))
    assert isinstance(reg_b, CellRegistered)
    [event] = registry.handle(DeclareCapability(cell_id=reg_b.cell.id, tag="t"))
    assert isinstance(event, CapabilityDeclared)
    assert event.tag_was_new is False


# ---------- refresh_capabilities ----------


def test_refresh_capabilities_bumps_last_refreshed_at_on_all_bindings():
    registry, cell = make_registry_with_cell()
    [d1] = registry.handle(DeclareCapability(cell_id=cell.id, tag="a", description="x"))
    [d2] = registry.handle(DeclareCapability(cell_id=cell.id, tag="b", description="y"))
    assert isinstance(d1, CapabilityDeclared)
    assert isinstance(d2, CapabilityDeclared)
    [event] = registry.handle(RefreshCapabilities(cell_id=cell.id))
    assert isinstance(event, CapabilitiesRefreshed)
    assert event.refreshed_count == 2
    bindings = {b.tag: b for b in registry.list_capabilities(cell_id=cell.id)}
    assert bindings["a"].last_refreshed_at > d1.binding.last_refreshed_at
    assert bindings["b"].last_refreshed_at > d2.binding.last_refreshed_at
    # declared_at is preserved.
    assert bindings["a"].declared_at == d1.binding.declared_at
    assert bindings["b"].declared_at == d2.binding.declared_at


def test_refresh_capabilities_with_no_bindings_returns_zero():
    registry, cell = make_registry_with_cell()
    [event] = registry.handle(RefreshCapabilities(cell_id=cell.id))
    assert isinstance(event, CapabilitiesRefreshed)
    assert event.refreshed_count == 0


def test_refresh_capabilities_only_touches_the_target_cell():
    registry, cell_a = make_registry_with_cell("cell_a")
    [reg_b] = registry.handle(RegisterCell(name="cell_b", purpose="y"))
    assert isinstance(reg_b, CellRegistered)
    [da] = registry.handle(
        DeclareCapability(cell_id=cell_a.id, tag="t", description="x")
    )
    [db] = registry.handle(DeclareCapability(cell_id=reg_b.cell.id, tag="t"))
    assert isinstance(da, CapabilityDeclared)
    assert isinstance(db, CapabilityDeclared)
    registry.handle(RefreshCapabilities(cell_id=cell_a.id))
    bindings = {b.cell_id: b for b in registry.list_capabilities()}
    assert bindings[cell_a.id].last_refreshed_at > da.binding.last_refreshed_at
    assert bindings[reg_b.cell.id].last_refreshed_at == db.binding.last_refreshed_at


def test_refresh_capabilities_unknown_cell_raises():
    registry = Registry(repository=InMemoryRepository(), now_factory=FakeClock().now)
    with pytest.raises(KeyError, match="Unknown cell"):
        registry.handle(RefreshCapabilities(cell_id="cell_missing"))


# ---------- list_capabilities ----------


def test_list_capabilities_empty_by_default():
    registry, _ = make_registry_with_cell()
    assert registry.list_capabilities() == []


def test_list_capabilities_returns_all_when_unfiltered():
    registry, cell_a = make_registry_with_cell("cell_a")
    [reg_b] = registry.handle(RegisterCell(name="cell_b", purpose="y"))
    assert isinstance(reg_b, CellRegistered)
    registry.handle(DeclareCapability(cell_id=cell_a.id, tag="a", description="x"))
    registry.handle(DeclareCapability(cell_id=reg_b.cell.id, tag="a"))
    bindings = registry.list_capabilities()
    assert {(b.cell_id, b.tag) for b in bindings} == {
        (cell_a.id, "a"),
        (reg_b.cell.id, "a"),
    }


def test_list_capabilities_filters_by_cell_id():
    registry, cell_a = make_registry_with_cell("cell_a")
    [reg_b] = registry.handle(RegisterCell(name="cell_b", purpose="y"))
    assert isinstance(reg_b, CellRegistered)
    registry.handle(DeclareCapability(cell_id=cell_a.id, tag="a", description="x"))
    registry.handle(DeclareCapability(cell_id=reg_b.cell.id, tag="a"))
    a_only = registry.list_capabilities(cell_id=cell_a.id)
    assert len(a_only) == 1
    assert a_only[0].cell_id == cell_a.id


def test_list_capabilities_returns_defensive_copies():
    """Mutating a returned binding must not affect the registry's view."""
    registry, cell = make_registry_with_cell()
    [event] = registry.handle(
        DeclareCapability(cell_id=cell.id, tag="t", description="x")
    )
    assert isinstance(event, CapabilityDeclared)
    bindings = registry.list_capabilities(cell_id=cell.id)
    bindings[0].last_refreshed_at = "tampered"
    fresh = registry.list_capabilities(cell_id=cell.id)
    assert fresh[0].last_refreshed_at != "tampered"


def test_capability_binding_dataclass_field_set():
    """Spot-check the binding shape — guards against accidental field
    drift in models.py that downstream PRs (sqlite, MCP) read from."""
    binding = CapabilityBinding(
        cell_id="cell_x", tag="t", declared_at="t1", last_refreshed_at="t2"
    )
    assert binding.cell_id == "cell_x"
    assert binding.tag == "t"
    assert binding.declared_at == "t1"
    assert binding.last_refreshed_at == "t2"
