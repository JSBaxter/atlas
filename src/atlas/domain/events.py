from __future__ import annotations

from dataclasses import dataclass, field

from .models import CapabilityBinding, Cell, Tag


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


@dataclass(slots=True)
class CapabilityDeclared:
    """Returned from ``declare_capability``.

    ``tag_was_new`` is ``True`` iff this call also auto-registered the
    tag. ``suggestions`` lists existing tag names close to the declared
    one for fragmentation prevention; empty until the similarity
    algorithm lands.
    """

    binding: CapabilityBinding
    tag: Tag
    tag_was_new: bool
    suggestions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CapabilityRevoked:
    """Returned from ``revoke_capability``.

    ``was_present`` is ``False`` when the cell had no binding for the
    tag — the call still succeeds (idempotent retract).
    """

    cell_id: str
    tag: str
    was_present: bool


@dataclass(slots=True)
class CapabilitiesRefreshed:
    """Returned from ``refresh_capabilities`` — the heartbeat path that
    bumps ``last_refreshed_at`` on all of a cell's bindings."""

    cell_id: str
    refreshed_count: int
