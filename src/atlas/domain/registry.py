from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from secrets import token_urlsafe
from typing import Protocol

from .commands import (
    DeclareCapability,
    RefreshCapabilities,
    RegisterCell,
    RevokeCapability,
    SetCellStatus,
)
from .events import (
    CapabilitiesRefreshed,
    CapabilityDeclared,
    CapabilityRevoked,
    CellInductionConflict,
    CellRegistered,
    CellStatusChanged,
)
from .models import CELL_STATUSES, CapabilityBinding, Cell, Tag


class AtlasRepository(Protocol):
    def add_cell(self, cell: Cell) -> None: ...
    def update_cell(self, cell: Cell) -> None: ...
    def get_cell(self, cell_id: str) -> Cell | None: ...
    def get_cell_by_name(self, name: str) -> Cell | None: ...
    def get_cell_by_induced_by(self, induced_by: str) -> Cell | None: ...
    def list_cells(self, status: str | None = None) -> list[Cell]: ...
    def add_tag(self, tag: Tag) -> None: ...
    def get_tag(self, name: str) -> Tag | None: ...
    def add_capability_binding(self, binding: CapabilityBinding) -> None: ...
    def update_capability_binding(self, binding: CapabilityBinding) -> None: ...
    def get_capability_binding(
        self, cell_id: str, tag: str
    ) -> CapabilityBinding | None: ...
    def list_capability_bindings(
        self, cell_id: str | None = None
    ) -> list[CapabilityBinding]: ...
    def delete_capability_binding(self, cell_id: str, tag: str) -> bool: ...


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
        if isinstance(command, DeclareCapability):
            return self._handle_declare_capability(command)
        if isinstance(command, RevokeCapability):
            return self._handle_revoke_capability(command)
        if isinstance(command, RefreshCapabilities):
            return self._handle_refresh_capabilities(command)
        raise TypeError(f"Unknown command: {type(command).__name__}")

    def get_cell(self, cell_id: str) -> Cell | None:
        return self.repository.get_cell(cell_id)

    def list_cells(self, status: str | None = None) -> list[Cell]:
        return self.repository.list_cells(status=status)

    def list_capabilities(self, cell_id: str | None = None) -> list[CapabilityBinding]:
        return self.repository.list_capability_bindings(cell_id=cell_id)

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

    def _handle_declare_capability(self, command: DeclareCapability) -> list[object]:
        cell = self._require_cell(command.cell_id)

        existing_tag = self.repository.get_tag(command.tag)
        tag_was_new = existing_tag is None

        if existing_tag is None:
            if command.description is None:
                raise ValueError(
                    f"Cannot declare new tag {command.tag!r} without a "
                    "description (descriptions are required only at first "
                    "registration)."
                )
            now = self.now_factory()
            tag = Tag(
                name=command.tag,
                description=command.description,
                registered_at=now,
                registered_by=cell.id,
                status="active",
            )
            self.repository.add_tag(tag)
        else:
            tag = existing_tag

        suggestions = self._suggest_similar_tags(command.tag)

        now = self.now_factory()
        existing_binding = self.repository.get_capability_binding(cell.id, command.tag)
        if existing_binding is not None:
            binding = replace(existing_binding, last_refreshed_at=now)
            self.repository.update_capability_binding(binding)
        else:
            binding = CapabilityBinding(
                cell_id=cell.id,
                tag=command.tag,
                declared_at=now,
                last_refreshed_at=now,
            )
            self.repository.add_capability_binding(binding)

        return [
            CapabilityDeclared(
                binding=binding,
                tag=tag,
                tag_was_new=tag_was_new,
                suggestions=suggestions,
            )
        ]

    def _handle_revoke_capability(self, command: RevokeCapability) -> list[object]:
        self._require_cell(command.cell_id)
        was_present = self.repository.delete_capability_binding(
            command.cell_id, command.tag
        )
        return [
            CapabilityRevoked(
                cell_id=command.cell_id, tag=command.tag, was_present=was_present
            )
        ]

    def _handle_refresh_capabilities(
        self, command: RefreshCapabilities
    ) -> list[object]:
        self._require_cell(command.cell_id)
        bindings = self.repository.list_capability_bindings(cell_id=command.cell_id)
        now = self.now_factory()
        for binding in bindings:
            self.repository.update_capability_binding(
                replace(binding, last_refreshed_at=now)
            )
        return [
            CapabilitiesRefreshed(
                cell_id=command.cell_id, refreshed_count=len(bindings)
            )
        ]

    def _suggest_similar_tags(self, name: str) -> list[str]:
        """Intentional stub. Returns ``[]`` until the similarity
        algorithm lands."""
        return []

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
