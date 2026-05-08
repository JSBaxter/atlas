from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RegisterCell:
    name: str
    purpose: str
    repo_url: str | None = None
    induced_by: str | None = None


@dataclass(slots=True)
class SetCellStatus:
    cell_id: str
    status: str
