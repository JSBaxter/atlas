from __future__ import annotations

import pytest

from atlas.domain import (
    AliasProposed,
    CapabilityDeclared,
    Cell,
    CellRegistered,
    DeclareCapability,
    DeprecateTag,
    ProposeAlias,
    RegisterCell,
    Registry,
    SetTagSchema,
    TagDeprecated,
    TagListing,
    TagSchemaSet,
)
from tests.fixtures import FakeClock, InMemoryRepository


def make_registry() -> Registry:
    return Registry(repository=InMemoryRepository(), now_factory=FakeClock().now)


def make_registry_with_cell(name: str = "cytometer") -> tuple[Registry, Cell]:
    registry = make_registry()
    [event] = registry.handle(RegisterCell(name=name, purpose="x"))
    assert isinstance(event, CellRegistered)
    return registry, event.cell


def declare(registry: Registry, cell_id: str, tag: str, description: str) -> None:
    [event] = registry.handle(
        DeclareCapability(cell_id=cell_id, tag=tag, description=description)
    )
    assert isinstance(event, CapabilityDeclared)


# ---------- deprecate_tag ----------


def test_deprecate_tag_marks_tag_deprecated():
    registry, cell = make_registry_with_cell()
    declare(registry, cell.id, "t", "x")
    [event] = registry.handle(DeprecateTag(tag="t"))
    assert isinstance(event, TagDeprecated)
    assert event.tag.name == "t"
    assert event.tag.status == "deprecated"
    assert event.tag.alias_to is None


def test_deprecate_tag_with_alias_to_sets_canonical_redirect():
    registry, cell = make_registry_with_cell()
    declare(registry, cell.id, "sast", "x")
    declare(registry, cell.id, "static-analysis", "y")
    [event] = registry.handle(DeprecateTag(tag="sast", alias_to="static-analysis"))
    assert isinstance(event, TagDeprecated)
    assert event.tag.status == "deprecated"
    assert event.tag.alias_to == "static-analysis"


def test_deprecate_tag_unknown_tag_raises():
    registry = make_registry()
    with pytest.raises(KeyError, match="Unknown tag"):
        registry.handle(DeprecateTag(tag="never-registered"))


def test_deprecate_tag_to_self_raises():
    registry, cell = make_registry_with_cell()
    declare(registry, cell.id, "t", "x")
    with pytest.raises(ValueError, match="alias tag 't' to itself"):
        registry.handle(DeprecateTag(tag="t", alias_to="t"))


def test_deprecate_tag_to_missing_canonical_raises():
    registry, cell = make_registry_with_cell()
    declare(registry, cell.id, "t", "x")
    with pytest.raises(ValueError, match="does not exist"):
        registry.handle(DeprecateTag(tag="t", alias_to="missing"))


def test_deprecate_tag_to_already_deprecated_canonical_raises():
    registry, cell = make_registry_with_cell()
    declare(registry, cell.id, "old", "x")
    declare(registry, cell.id, "older", "y")
    registry.handle(DeprecateTag(tag="older"))
    # Now try to deprecate "old" with alias_to=already-deprecated "older"
    with pytest.raises(ValueError, match="not active"):
        registry.handle(DeprecateTag(tag="old", alias_to="older"))


# ---------- propose_alias ----------


def test_propose_alias_updates_alias_on_deprecated_tag():
    registry, cell = make_registry_with_cell()
    declare(registry, cell.id, "old", "x")
    declare(registry, cell.id, "new1", "y")
    declare(registry, cell.id, "new2", "z")
    registry.handle(DeprecateTag(tag="old", alias_to="new1"))
    [event] = registry.handle(ProposeAlias(deprecated="old", canonical="new2"))
    assert isinstance(event, AliasProposed)
    assert event.tag.alias_to == "new2"
    assert event.tag.status == "deprecated"


def test_propose_alias_missing_deprecated_raises():
    registry = make_registry()
    with pytest.raises(KeyError, match="Unknown tag"):
        registry.handle(ProposeAlias(deprecated="missing", canonical="x"))


def test_propose_alias_missing_canonical_raises():
    registry, cell = make_registry_with_cell()
    declare(registry, cell.id, "t", "x")
    with pytest.raises(ValueError, match="does not exist"):
        registry.handle(ProposeAlias(deprecated="t", canonical="missing"))


def test_propose_alias_self_alias_raises():
    registry, cell = make_registry_with_cell()
    declare(registry, cell.id, "t", "x")
    with pytest.raises(ValueError, match="itself"):
        registry.handle(ProposeAlias(deprecated="t", canonical="t"))


def test_propose_alias_to_deprecated_canonical_raises():
    registry, cell = make_registry_with_cell()
    declare(registry, cell.id, "t1", "x")
    declare(registry, cell.id, "t2", "y")
    registry.handle(DeprecateTag(tag="t2"))
    with pytest.raises(ValueError, match="not active"):
        registry.handle(ProposeAlias(deprecated="t1", canonical="t2"))


# ---------- set_tag_schema ----------


def test_set_tag_schema_attaches_schema():
    registry, cell = make_registry_with_cell()
    declare(registry, cell.id, "t", "x")
    schema = {"type": "object", "properties": {"path": {"type": "string"}}}
    [event] = registry.handle(SetTagSchema(tag="t", schema=schema))
    assert isinstance(event, TagSchemaSet)
    assert event.tag.payload_schema == schema


def test_set_tag_schema_overwrites_existing():
    registry, cell = make_registry_with_cell()
    declare(registry, cell.id, "t", "x")
    registry.handle(SetTagSchema(tag="t", schema={"type": "object"}))
    [event] = registry.handle(SetTagSchema(tag="t", schema={"type": "array"}))
    assert isinstance(event, TagSchemaSet)
    assert event.tag.payload_schema == {"type": "array"}


def test_set_tag_schema_can_clear_with_none():
    registry, cell = make_registry_with_cell()
    declare(registry, cell.id, "t", "x")
    registry.handle(SetTagSchema(tag="t", schema={"type": "object"}))
    [event] = registry.handle(SetTagSchema(tag="t", schema=None))
    assert isinstance(event, TagSchemaSet)
    assert event.tag.payload_schema is None


def test_set_tag_schema_unknown_tag_raises():
    registry = make_registry()
    with pytest.raises(KeyError, match="Unknown tag"):
        registry.handle(SetTagSchema(tag="never-registered", schema={"a": 1}))


# ---------- list_tags ----------


def test_list_tags_empty_when_no_tags():
    registry = make_registry()
    assert registry.list_tags() == []


def test_list_tags_returns_listings_with_usage_counts():
    registry, cell_a = make_registry_with_cell("cell_a")
    [reg_b] = registry.handle(RegisterCell(name="cell_b", purpose="y"))
    assert isinstance(reg_b, CellRegistered)
    declare(registry, cell_a.id, "shared", "x")
    declare(registry, reg_b.cell.id, "shared", "ignored-second-desc")
    declare(registry, cell_a.id, "solo", "y")

    listings = {entry.tag.name: entry for entry in registry.list_tags()}
    assert listings["shared"].usage_count == 2
    assert listings["solo"].usage_count == 1


def test_list_tags_filters_by_status():
    registry, cell = make_registry_with_cell()
    declare(registry, cell.id, "active-tag", "x")
    declare(registry, cell.id, "old-tag", "y")
    registry.handle(DeprecateTag(tag="old-tag"))

    actives = registry.list_tags(status="active")
    deprecateds = registry.list_tags(status="deprecated")
    assert {entry.tag.name for entry in actives} == {"active-tag"}
    assert {entry.tag.name for entry in deprecateds} == {"old-tag"}


def test_list_tags_usage_count_is_distinct_cells():
    """A cell can only have one binding per tag (PRIMARY KEY enforces);
    the count is the number of distinct cells, not bindings."""
    registry, cell = make_registry_with_cell()
    declare(registry, cell.id, "t", "x")
    # Re-declare from the same cell — still one cell.
    declare(registry, cell.id, "t", "x")
    [(listing,)] = [(entry,) for entry in registry.list_tags()]
    assert listing.tag.name == "t"
    assert listing.usage_count == 1


def test_list_tags_returns_tag_listing_view_type():
    registry, cell = make_registry_with_cell()
    declare(registry, cell.id, "t", "x")
    [listing] = registry.list_tags()
    assert isinstance(listing, TagListing)
    assert listing.tag.name == "t"


# ---------- get_tag_schema ----------


def test_get_tag_schema_returns_none_for_unknown_tag():
    registry = make_registry()
    assert registry.get_tag_schema("missing") is None


def test_get_tag_schema_returns_none_when_no_schema_set():
    registry, cell = make_registry_with_cell()
    declare(registry, cell.id, "t", "x")
    assert registry.get_tag_schema("t") is None


def test_get_tag_schema_returns_attached_schema():
    registry, cell = make_registry_with_cell()
    declare(registry, cell.id, "t", "x")
    schema = {"type": "object", "required": ["path"]}
    registry.handle(SetTagSchema(tag="t", schema=schema))
    assert registry.get_tag_schema("t") == schema
