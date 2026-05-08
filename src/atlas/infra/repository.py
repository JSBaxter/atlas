from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from atlas.domain.models import CapabilityBinding, Cell, Tag


class SQLiteRepository:
    """Persistent ``AtlasRepository`` backed by SQLite.

    Mirrors the in-memory test fixture's contract; substituting one for
    the other is a one-line change at construction time.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        db_path: str | None = None,
    ) -> None:
        self.connection = connection
        self.db_path = db_path
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    @classmethod
    def connect(cls, db_path: str | Path) -> SQLiteRepository:
        connection = sqlite3.connect(str(db_path), check_same_thread=False)
        repository = cls(connection, db_path=str(db_path))
        repository.init_schema()
        return repository

    def init_schema(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        self.connection.executescript(schema_path.read_text())
        self.connection.commit()

    # ----- cells -----

    def add_cell(self, cell: Cell) -> None:
        self.connection.execute(
            """
            INSERT INTO cells (
                id, name, purpose, repo_url, registered_at, status, induced_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cell.id,
                cell.name,
                cell.purpose,
                cell.repo_url,
                cell.registered_at,
                cell.status,
                cell.induced_by,
            ),
        )
        self.connection.commit()

    def update_cell(self, cell: Cell) -> None:
        self.connection.execute(
            """
            UPDATE cells
            SET name = ?, purpose = ?, repo_url = ?, registered_at = ?,
                status = ?, induced_by = ?
            WHERE id = ?
            """,
            (
                cell.name,
                cell.purpose,
                cell.repo_url,
                cell.registered_at,
                cell.status,
                cell.induced_by,
                cell.id,
            ),
        )
        self.connection.commit()

    def get_cell(self, cell_id: str) -> Cell | None:
        row = self.connection.execute(
            "SELECT * FROM cells WHERE id = ?", (cell_id,)
        ).fetchone()
        return self._row_to_cell(row) if row is not None else None

    def get_cell_by_name(self, name: str) -> Cell | None:
        row = self.connection.execute(
            "SELECT * FROM cells WHERE name = ?", (name,)
        ).fetchone()
        return self._row_to_cell(row) if row is not None else None

    def get_cell_by_induced_by(self, induced_by: str) -> Cell | None:
        row = self.connection.execute(
            "SELECT * FROM cells WHERE induced_by = ?", (induced_by,)
        ).fetchone()
        return self._row_to_cell(row) if row is not None else None

    def list_cells(self, status: str | None = None) -> list[Cell]:
        if status is None:
            rows = self.connection.execute("SELECT * FROM cells").fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM cells WHERE status = ?", (status,)
            ).fetchall()
        return [self._row_to_cell(row) for row in rows]

    # ----- tags -----

    def add_tag(self, tag: Tag) -> None:
        self.connection.execute(
            """
            INSERT INTO tags (
                name, description, status, alias_to, payload_schema,
                registered_at, registered_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tag.name,
                tag.description,
                tag.status,
                tag.alias_to,
                self._dump_schema(tag.payload_schema),
                tag.registered_at,
                tag.registered_by,
            ),
        )
        self.connection.commit()

    def update_tag(self, tag: Tag) -> None:
        self.connection.execute(
            """
            UPDATE tags
            SET description = ?, status = ?, alias_to = ?,
                payload_schema = ?, registered_at = ?, registered_by = ?
            WHERE name = ?
            """,
            (
                tag.description,
                tag.status,
                tag.alias_to,
                self._dump_schema(tag.payload_schema),
                tag.registered_at,
                tag.registered_by,
                tag.name,
            ),
        )
        self.connection.commit()

    def get_tag(self, name: str) -> Tag | None:
        row = self.connection.execute(
            "SELECT * FROM tags WHERE name = ?", (name,)
        ).fetchone()
        return self._row_to_tag(row) if row is not None else None

    def list_tags(self, status: str | None = None) -> list[Tag]:
        if status is None:
            rows = self.connection.execute("SELECT * FROM tags").fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM tags WHERE status = ?", (status,)
            ).fetchall()
        return [self._row_to_tag(row) for row in rows]

    # ----- capability bindings -----

    def add_capability_binding(self, binding: CapabilityBinding) -> None:
        self.connection.execute(
            """
            INSERT INTO capability_bindings (
                cell_id, tag, declared_at, last_refreshed_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                binding.cell_id,
                binding.tag,
                binding.declared_at,
                binding.last_refreshed_at,
            ),
        )
        self.connection.commit()

    def update_capability_binding(self, binding: CapabilityBinding) -> None:
        self.connection.execute(
            """
            UPDATE capability_bindings
            SET declared_at = ?, last_refreshed_at = ?
            WHERE cell_id = ? AND tag = ?
            """,
            (
                binding.declared_at,
                binding.last_refreshed_at,
                binding.cell_id,
                binding.tag,
            ),
        )
        self.connection.commit()

    def get_capability_binding(
        self, cell_id: str, tag: str
    ) -> CapabilityBinding | None:
        row = self.connection.execute(
            """
            SELECT * FROM capability_bindings
            WHERE cell_id = ? AND tag = ?
            """,
            (cell_id, tag),
        ).fetchone()
        return self._row_to_binding(row) if row is not None else None

    def list_capability_bindings(
        self, cell_id: str | None = None
    ) -> list[CapabilityBinding]:
        if cell_id is None:
            rows = self.connection.execute(
                "SELECT * FROM capability_bindings"
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM capability_bindings WHERE cell_id = ?",
                (cell_id,),
            ).fetchall()
        return [self._row_to_binding(row) for row in rows]

    def delete_capability_binding(self, cell_id: str, tag: str) -> bool:
        cursor = self.connection.execute(
            """
            DELETE FROM capability_bindings
            WHERE cell_id = ? AND tag = ?
            """,
            (cell_id, tag),
        )
        self.connection.commit()
        return cursor.rowcount > 0

    # ----- row mappers -----

    @staticmethod
    def _row_to_cell(row: sqlite3.Row) -> Cell:
        return Cell(
            id=row["id"],
            name=row["name"],
            purpose=row["purpose"],
            repo_url=row["repo_url"],
            registered_at=row["registered_at"],
            status=row["status"],
            induced_by=row["induced_by"],
        )

    @classmethod
    def _row_to_tag(cls, row: sqlite3.Row) -> Tag:
        return Tag(
            name=row["name"],
            description=row["description"],
            registered_at=row["registered_at"],
            registered_by=row["registered_by"],
            status=row["status"],
            alias_to=row["alias_to"],
            payload_schema=cls._load_schema(row["payload_schema"]),
        )

    @staticmethod
    def _row_to_binding(row: sqlite3.Row) -> CapabilityBinding:
        return CapabilityBinding(
            cell_id=row["cell_id"],
            tag=row["tag"],
            declared_at=row["declared_at"],
            last_refreshed_at=row["last_refreshed_at"],
        )

    @staticmethod
    def _dump_schema(schema: dict[str, Any] | None) -> str | None:
        return None if schema is None else json.dumps(schema)

    @staticmethod
    def _load_schema(stored: str | None) -> dict[str, Any] | None:
        return None if stored is None else json.loads(stored)
