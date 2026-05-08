from __future__ import annotations

from dataclasses import replace

from atlas.domain.models import CapabilityBinding, Cell, Tag


class InMemoryRepository:
    """Test double for :class:`atlas.domain.registry.AtlasRepository`.

    Stores defensive copies on read and write so callers can't mutate
    the in-store record by accident.
    """

    def __init__(self) -> None:
        self.cells: dict[str, Cell] = {}
        self.tags: dict[str, Tag] = {}
        self.bindings: dict[tuple[str, str], CapabilityBinding] = {}

    def add_cell(self, cell: Cell) -> None:
        self.cells[cell.id] = replace(cell)

    def update_cell(self, cell: Cell) -> None:
        self.cells[cell.id] = replace(cell)

    def get_cell(self, cell_id: str) -> Cell | None:
        cell = self.cells.get(cell_id)
        return replace(cell) if cell is not None else None

    def get_cell_by_name(self, name: str) -> Cell | None:
        for cell in self.cells.values():
            if cell.name == name:
                return replace(cell)
        return None

    def get_cell_by_induced_by(self, induced_by: str) -> Cell | None:
        for cell in self.cells.values():
            if cell.induced_by == induced_by:
                return replace(cell)
        return None

    def list_cells(self, status: str | None = None) -> list[Cell]:
        cells = [replace(cell) for cell in self.cells.values()]
        if status is not None:
            cells = [cell for cell in cells if cell.status == status]
        return cells

    def add_tag(self, tag: Tag) -> None:
        self.tags[tag.name] = replace(tag)

    def update_tag(self, tag: Tag) -> None:
        self.tags[tag.name] = replace(tag)

    def get_tag(self, name: str) -> Tag | None:
        tag = self.tags.get(name)
        return replace(tag) if tag is not None else None

    def list_tags(self, status: str | None = None) -> list[Tag]:
        tags = [replace(tag) for tag in self.tags.values()]
        if status is not None:
            tags = [tag for tag in tags if tag.status == status]
        return tags

    def add_capability_binding(self, binding: CapabilityBinding) -> None:
        self.bindings[(binding.cell_id, binding.tag)] = replace(binding)

    def update_capability_binding(self, binding: CapabilityBinding) -> None:
        self.bindings[(binding.cell_id, binding.tag)] = replace(binding)

    def get_capability_binding(
        self, cell_id: str, tag: str
    ) -> CapabilityBinding | None:
        binding = self.bindings.get((cell_id, tag))
        return replace(binding) if binding is not None else None

    def list_capability_bindings(
        self, cell_id: str | None = None
    ) -> list[CapabilityBinding]:
        bindings = [replace(binding) for binding in self.bindings.values()]
        if cell_id is not None:
            bindings = [binding for binding in bindings if binding.cell_id == cell_id]
        return bindings

    def delete_capability_binding(self, cell_id: str, tag: str) -> bool:
        return self.bindings.pop((cell_id, tag), None) is not None


class FakeClock:
    """Monotonic ISO-8601 timestamps for deterministic tests."""

    def __init__(self) -> None:
        self._tick = 0

    def now(self) -> str:
        self._tick += 1
        return f"2026-05-08T12:00:{self._tick:02d}+00:00"
