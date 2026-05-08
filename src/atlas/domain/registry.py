from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from secrets import token_urlsafe
from typing import Protocol

from .commands import RegisterCell, SetCellStatus
from .events import (
    CellInductionConflict,
    CellRegistered,
    CellStatusChanged,
)
from .models import CELL_STATUSES, Cell


class AtlasRepository(Protocol):
    def add_cell(self, cell: Cell) -> None: ...
    def update_cell(self, cell: Cell) -> None: ...
    def get_cell(self, cell_id: str) -> Cell | None: ...
    def get_cell_by_name(self, name: str) -> Cell | None: ...
    def get_cell_by_induced_by(self, induced_by: str) -> Cell | None: ...
    def list_cells(self, status: str | None = None) -> list[Cell]: ...


class Registry:
    """Storage-agnostic atlas service.

    Mutations come in as command dataclasses dispatched through
    :meth:`handle`; queries are direct method calls. The handler returns
    a list of result-shaped events (not persisted — atlas mutates
    in-place per SPEC.md).
    """

    def __init__(
        self,
        repository: AtlasRepository,
        now_factory: Callable[[], str] | None = None,
    ) -> None:
        self.repository = repository
        self.now_factory = now_factory or self._now

    def handle(self, command: object) -> list[object]:
        if isinstance(command, RegisterCell):
            return self._handle_register_cell(command)
        if isinstance(command, SetCellStatus):
            return self._handle_set_cell_status(command)
        raise TypeError(f"Unknown command: {type(command).__name__}")

    def get_cell(self, cell_id: str) -> Cell | None:
        return self.repository.get_cell(cell_id)

    def list_cells(self, status: str | None = None) -> list[Cell]:
        return self.repository.list_cells(status=status)

    def _handle_register_cell(self, command: RegisterCell) -> list[object]:
        existing_by_name = self.repository.get_cell_by_name(command.name)
        if existing_by_name is not None:
            return [CellRegistered(cell=existing_by_name, was_existing=True)]

        if command.induced_by is not None:
            existing_by_induced = self.repository.get_cell_by_induced_by(
                command.induced_by
            )
            if existing_by_induced is not None:
                return [
                    CellInductionConflict(
                        attempted_name=command.name,
                        induced_by=command.induced_by,
                        existing_cell=existing_by_induced,
                    )
                ]

        now = self.now_factory()
        cell = Cell(
            id=self._new_id("cell"),
            name=command.name,
            purpose=command.purpose,
            repo_url=command.repo_url,
            registered_at=now,
            status="active",
            induced_by=command.induced_by,
        )
        self.repository.add_cell(cell)
        return [CellRegistered(cell=cell, was_existing=False)]

    def _handle_set_cell_status(self, command: SetCellStatus) -> list[object]:
        if command.status not in CELL_STATUSES:
            raise ValueError(
                f"Invalid cell status: {command.status!r}. "
                f"Expected one of {sorted(CELL_STATUSES)}."
            )
        cell = self._require_cell(command.cell_id)
        if cell.status == command.status:
            return [CellStatusChanged(cell=cell)]
        updated = replace(cell, status=command.status)
        self.repository.update_cell(updated)
        return [CellStatusChanged(cell=updated)]

    def _require_cell(self, cell_id: str) -> Cell:
        cell = self.repository.get_cell(cell_id)
        if cell is None:
            raise KeyError(f"Unknown cell: {cell_id}")
        return cell

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{token_urlsafe(4).lower()}"

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
