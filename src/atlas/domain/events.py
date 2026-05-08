from __future__ import annotations

from dataclasses import dataclass

from .models import Cell


@dataclass(slots=True)
class CellRegistered:
    """Returned from ``register_cell``.

    ``was_existing`` is ``True`` when the call was idempotent (a cell with
    the given name already existed and was returned unchanged), ``False``
    when a fresh cell was created.
    """

    cell: Cell
    was_existing: bool


@dataclass(slots=True)
class CellInductionConflict:
    """Returned from ``register_cell`` when ``induced_by`` is already
    bound to a different cell.

    Resolves spawn-race conditions at register time: only the first
    register_cell call with a given induced_by wins; subsequent attempts
    surface the existing cell so the loser can adopt it instead of
    creating a duplicate.
    """

    attempted_name: str
    induced_by: str
    existing_cell: Cell


@dataclass(slots=True)
class CellStatusChanged:
    cell: Cell
