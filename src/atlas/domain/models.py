from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CELL_STATUSES: frozenset[str] = frozenset({"active", "inactive"})
TAG_STATUSES: frozenset[str] = frozenset({"active", "deprecated"})


@dataclass(slots=True)
class Cell:
    id: str
    name: str
    purpose: str
    repo_url: str | None
    registered_at: str
    status: str = "active"
    induced_by: str | None = None


@dataclass(slots=True)
class Tag:
    name: str
    description: str
    registered_at: str
    registered_by: str
    status: str = "active"
    alias_to: str | None = None
    payload_schema: dict[str, Any] | None = None


@dataclass(slots=True)
class CapabilityBinding:
    cell_id: str
    tag: str
    declared_at: str
    last_refreshed_at: str


@dataclass(slots=True)
class TagListing:
    """View returned by ``list_tags`` — bundles a tag with its
    usage count (number of distinct cells with bindings to it)."""

    tag: Tag
    usage_count: int
