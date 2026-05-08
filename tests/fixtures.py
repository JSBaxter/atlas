from __future__ import annotations

from dataclasses import replace

from atlas.domain.models import Cell


class InMemoryRepository:
    """Test double for :class:`atlas.domain.registry.AtlasRepository`.

    Stores defensive copies on read and write so callers can't mutate
    the in-store record by accident.
    """

    def __init__(self) -> None:
        self.cells: dict[str, Cell] = {}

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


class FakeClock:
    """Monotonic ISO-8601 timestamps for deterministic tests."""

    def __init__(self) -> None:
        self._tick = 0

    def now(self) -> str:
        self._tick += 1
        return f"2026-05-08T12:00:{self._tick:02d}+00:00"
