from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest

from atlas.domain.models import CapabilityBinding, Cell, Tag
from atlas.infra import SQLiteRepository


def make_repository() -> SQLiteRepository:
    connection = sqlite3.connect(":memory:")
    repository = SQLiteRepository(connection)
    repository.init_schema()
    return repository


# ---------- cell round-trips ----------


def test_round_trip_cell_with_all_fields():
    repo = make_repository()
    cell = Cell(
        id="cell_a4f",
        name="cytometer",
        purpose="cell counts",
        repo_url="git@github.com:JSBaxter/cytometer",
        registered_at="2026-05-08T12:00:01+00:00",
        status="active",
        induced_by=None,
    )
    repo.add_cell(cell)
    fetched = repo.get_cell(cell.id)
    assert fetched == cell


def test_round_trip_cell_with_optional_fields_none():
    repo = make_repository()
    cell = Cell(
        id="cell_x",
        name="minimal",
        purpose="p",
        repo_url=None,
        registered_at="2026-05-08T12:00:01+00:00",
        induced_by=None,
    )
    repo.add_cell(cell)
    assert repo.get_cell(cell.id) == cell


def test_round_trip_cell_with_induced_by():
    repo = make_repository()
    cell = Cell(
        id="cell_y",
        name="spawn",
        purpose="p",
        repo_url=None,
        registered_at="2026-05-08T12:00:01+00:00",
        induced_by="morph_42",
    )
    repo.add_cell(cell)
    assert repo.get_cell_by_induced_by("morph_42") == cell


def test_get_cell_by_name():
    repo = make_repository()
    cell = Cell(
        id="cell_x",
        name="alpha",
        purpose="p",
        repo_url=None,
        registered_at="2026-05-08T12:00:01+00:00",
    )
    repo.add_cell(cell)
    assert repo.get_cell_by_name("alpha") == cell
    assert repo.get_cell_by_name("missing") is None


def test_update_cell_changes_status():
    repo = make_repository()
    cell = Cell(
        id="cell_x",
        name="c",
        purpose="p",
        repo_url=None,
        registered_at="2026-05-08T12:00:01+00:00",
    )
    repo.add_cell(cell)
    repo.update_cell(replace(cell, status="inactive"))
    fetched = repo.get_cell(cell.id)
    assert fetched is not None
    assert fetched.status == "inactive"


def test_list_cells_filters_by_status():
    repo = make_repository()
    repo.add_cell(_cell("a", "alpha"))
    repo.add_cell(_cell("b", "beta"))
    repo.add_cell(replace(_cell("c", "gamma"), status="inactive"))

    actives = sorted(repo.list_cells(status="active"), key=lambda c: c.name)
    assert [c.name for c in actives] == ["alpha", "beta"]
    assert [c.name for c in repo.list_cells(status="inactive")] == ["gamma"]
    assert len(repo.list_cells()) == 3


def test_unique_induced_by_constraint_enforced():
    """Two cells with the same induced_by must collide at the index
    layer (matches SPEC's spawn-race protection)."""
    repo = make_repository()
    repo.add_cell(
        Cell(
            id="cell_a",
            name="a",
            purpose="p",
            repo_url=None,
            registered_at="2026-05-08T12:00:01+00:00",
            induced_by="morph_42",
        )
    )
    with pytest.raises(sqlite3.IntegrityError):
        repo.add_cell(
            Cell(
                id="cell_b",
                name="b",
                purpose="p",
                repo_url=None,
                registered_at="2026-05-08T12:00:02+00:00",
                induced_by="morph_42",
            )
        )


def test_unique_induced_by_constraint_allows_multiple_nulls():
    """Cells without induced_by don't collide."""
    repo = make_repository()
    repo.add_cell(_cell("a", "alpha"))
    repo.add_cell(_cell("b", "beta"))


# ---------- tag round-trips ----------


def test_round_trip_tag_with_payload_schema():
    repo = make_repository()
    repo.add_cell(_cell("c", "owner"))
    schema = {"type": "object", "properties": {"path": {"type": "string"}}}
    tag = Tag(
        name="static-analysis",
        description="finds bugs",
        registered_at="2026-05-08T12:00:01+00:00",
        registered_by="c",
        status="active",
        alias_to=None,
        payload_schema=schema,
    )
    repo.add_tag(tag)
    fetched = repo.get_tag("static-analysis")
    assert fetched is not None
    assert fetched.payload_schema == schema


def test_round_trip_tag_with_no_schema():
    repo = make_repository()
    repo.add_cell(_cell("c", "owner"))
    tag = Tag(
        name="t",
        description="d",
        registered_at="2026-05-08T12:00:01+00:00",
        registered_by="c",
    )
    repo.add_tag(tag)
    fetched = repo.get_tag("t")
    assert fetched is not None
    assert fetched.payload_schema is None


def test_update_tag_marks_deprecated_with_alias():
    repo = make_repository()
    repo.add_cell(_cell("c", "owner"))
    repo.add_tag(_tag("canonical", "c"))
    repo.add_tag(_tag("old", "c"))
    repo.update_tag(
        replace(_tag("old", "c"), status="deprecated", alias_to="canonical")
    )
    fetched = repo.get_tag("old")
    assert fetched is not None
    assert fetched.status == "deprecated"
    assert fetched.alias_to == "canonical"


def test_list_tags_filters_by_status():
    repo = make_repository()
    repo.add_cell(_cell("c", "owner"))
    repo.add_tag(_tag("alive", "c"))
    repo.add_tag(_tag("dead", "c"))
    repo.update_tag(replace(_tag("dead", "c"), status="deprecated"))
    assert {t.name for t in repo.list_tags(status="active")} == {"alive"}
    assert {t.name for t in repo.list_tags(status="deprecated")} == {"dead"}
    assert len(repo.list_tags()) == 2


# ---------- capability binding round-trips ----------


def test_round_trip_capability_binding():
    repo = make_repository()
    repo.add_cell(_cell("c", "owner"))
    repo.add_tag(_tag("t", "c"))
    binding = CapabilityBinding(
        cell_id="c",
        tag="t",
        declared_at="2026-05-08T12:00:01+00:00",
        last_refreshed_at="2026-05-08T12:00:01+00:00",
    )
    repo.add_capability_binding(binding)
    assert repo.get_capability_binding("c", "t") == binding


def test_update_capability_binding_bumps_refreshed_at():
    repo = make_repository()
    repo.add_cell(_cell("c", "owner"))
    repo.add_tag(_tag("t", "c"))
    binding = CapabilityBinding(
        cell_id="c",
        tag="t",
        declared_at="2026-05-08T12:00:01+00:00",
        last_refreshed_at="2026-05-08T12:00:01+00:00",
    )
    repo.add_capability_binding(binding)
    repo.update_capability_binding(
        CapabilityBinding(
            cell_id="c",
            tag="t",
            declared_at="2026-05-08T12:00:01+00:00",
            last_refreshed_at="2026-05-09T12:00:00+00:00",
        )
    )
    fetched = repo.get_capability_binding("c", "t")
    assert fetched is not None
    assert fetched.last_refreshed_at == "2026-05-09T12:00:00+00:00"
    assert fetched.declared_at == "2026-05-08T12:00:01+00:00"


def test_delete_capability_binding_returns_true_when_present():
    repo = make_repository()
    repo.add_cell(_cell("c", "owner"))
    repo.add_tag(_tag("t", "c"))
    repo.add_capability_binding(
        CapabilityBinding(
            cell_id="c",
            tag="t",
            declared_at="2026-05-08T12:00:01+00:00",
            last_refreshed_at="2026-05-08T12:00:01+00:00",
        )
    )
    assert repo.delete_capability_binding("c", "t") is True
    assert repo.get_capability_binding("c", "t") is None


def test_delete_capability_binding_returns_false_when_absent():
    repo = make_repository()
    assert repo.delete_capability_binding("missing-cell", "missing-tag") is False


def test_list_capability_bindings_filters_by_cell_id():
    repo = make_repository()
    repo.add_cell(_cell("a", "alpha"))
    repo.add_cell(_cell("b", "beta"))
    repo.add_tag(_tag("t", "a"))
    repo.add_capability_binding(
        CapabilityBinding(
            cell_id="a",
            tag="t",
            declared_at="2026-05-08T12:00:01+00:00",
            last_refreshed_at="2026-05-08T12:00:01+00:00",
        )
    )
    repo.add_capability_binding(
        CapabilityBinding(
            cell_id="b",
            tag="t",
            declared_at="2026-05-08T12:00:01+00:00",
            last_refreshed_at="2026-05-08T12:00:01+00:00",
        )
    )
    a_only = repo.list_capability_bindings(cell_id="a")
    assert [b.cell_id for b in a_only] == ["a"]
    assert len(repo.list_capability_bindings()) == 2


def test_capability_binding_foreign_key_enforced_for_unknown_cell():
    repo = make_repository()
    repo.add_cell(_cell("c", "owner"))
    repo.add_tag(_tag("t", "c"))
    with pytest.raises(sqlite3.IntegrityError):
        repo.add_capability_binding(
            CapabilityBinding(
                cell_id="missing-cell",
                tag="t",
                declared_at="2026-05-08T12:00:01+00:00",
                last_refreshed_at="2026-05-08T12:00:01+00:00",
            )
        )


def test_capability_binding_primary_key_prevents_duplicates():
    repo = make_repository()
    repo.add_cell(_cell("c", "owner"))
    repo.add_tag(_tag("t", "c"))
    binding = CapabilityBinding(
        cell_id="c",
        tag="t",
        declared_at="2026-05-08T12:00:01+00:00",
        last_refreshed_at="2026-05-08T12:00:01+00:00",
    )
    repo.add_capability_binding(binding)
    with pytest.raises(sqlite3.IntegrityError):
        repo.add_capability_binding(binding)


# ---------- persistence across reconnects ----------


def test_data_persists_across_reconnect(tmp_path):
    db_path = tmp_path / "atlas.db"
    repo = SQLiteRepository.connect(db_path)
    repo.add_cell(_cell("c", "owner"))
    repo.connection.close()

    reopened = SQLiteRepository.connect(db_path)
    fetched = reopened.get_cell("c")
    assert fetched is not None
    assert fetched.name == "owner"


# ---------- helpers ----------


def _cell(cell_id: str, name: str) -> Cell:
    return Cell(
        id=cell_id,
        name=name,
        purpose="p",
        repo_url=None,
        registered_at="2026-05-08T12:00:01+00:00",
    )


def _tag(name: str, registered_by: str) -> Tag:
    return Tag(
        name=name,
        description="d",
        registered_at="2026-05-08T12:00:01+00:00",
        registered_by=registered_by,
    )
