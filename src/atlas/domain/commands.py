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


@dataclass(slots=True)
class DeclareCapability:
    cell_id: str
    tag: str
    description: str | None = None


@dataclass(slots=True)
class RevokeCapability:
    cell_id: str
    tag: str


@dataclass(slots=True)
class RefreshCapabilities:
    cell_id: str
