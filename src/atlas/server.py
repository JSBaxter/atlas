from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from typing import Any, cast

from fastmcp import FastMCP

from atlas.domain.commands import (
    DeclareCapability,
    DeprecateTag,
    ProposeAlias,
    RefreshCapabilities,
    RegisterCell,
    RevokeCapability,
    SetCellStatus,
    SetTagSchema,
)
from atlas.domain.registry import Registry
from atlas.infra.repository import SQLiteRepository


def create_registry(db_path: str = "./atlas.db") -> Registry:
    repository = SQLiteRepository.connect(db_path)
    return Registry(repository=repository)


def create_app(db_path: str = "./atlas.db") -> FastMCP:
    registry = create_registry(db_path)
    app = FastMCP(
        name="atlas",
        instructions=(
            "Colony registry. Use it to register cells, declare and discover "
            "capabilities, manage the controlled tag vocabulary, and look up "
            "which cells can do what."
        ),
    )

    # -- Cell lifecycle --------------------------------------------------------

    @app.tool()
    def register_cell(
        name: str,
        purpose: str,
        repo_url: str | None = None,
        induced_by: str | None = None,
    ) -> list[dict[str, Any]]:
        return _serialize_events(
            registry.handle(
                RegisterCell(
                    name=name,
                    purpose=purpose,
                    repo_url=repo_url,
                    induced_by=induced_by,
                )
            )
        )

    @app.tool()
    def set_cell_status(cell_id: str, status: str) -> list[dict[str, Any]]:
        return _serialize_events(
            registry.handle(SetCellStatus(cell_id=cell_id, status=status))
        )

    @app.tool()
    def get_cell(cell_id: str) -> dict[str, Any] | None:
        cell = registry.get_cell(cell_id)
        return _serialize(cell) if cell is not None else None

    @app.tool()
    def list_cells(status: str | None = None) -> list[dict[str, Any]]:
        return [_serialize(c) for c in registry.list_cells(status=status)]

    # -- Capability declarations -----------------------------------------------

    @app.tool()
    def declare_capability(
        cell_id: str,
        tag: str,
        description: str | None = None,
    ) -> list[dict[str, Any]]:
        return _serialize_events(
            registry.handle(
                DeclareCapability(
                    cell_id=cell_id,
                    tag=tag,
                    description=description,
                )
            )
        )

    @app.tool()
    def revoke_capability(cell_id: str, tag: str) -> list[dict[str, Any]]:
        return _serialize_events(
            registry.handle(RevokeCapability(cell_id=cell_id, tag=tag))
        )

    @app.tool()
    def refresh_capabilities(cell_id: str) -> list[dict[str, Any]]:
        return _serialize_events(registry.handle(RefreshCapabilities(cell_id=cell_id)))

    @app.tool()
    def list_capabilities(cell_id: str | None = None) -> list[dict[str, Any]]:
        return [_serialize(b) for b in registry.list_capabilities(cell_id=cell_id)]

    # -- Registry admin --------------------------------------------------------

    @app.tool()
    def list_tags(status: str | None = None) -> list[dict[str, Any]]:
        return [_serialize(tl) for tl in registry.list_tags(status=status)]

    @app.tool()
    def deprecate_tag(
        tag: str,
        alias_to: str | None = None,
    ) -> list[dict[str, Any]]:
        return _serialize_events(
            registry.handle(DeprecateTag(tag=tag, alias_to=alias_to))
        )

    @app.tool()
    def propose_alias(deprecated: str, canonical: str) -> list[dict[str, Any]]:
        return _serialize_events(
            registry.handle(ProposeAlias(deprecated=deprecated, canonical=canonical))
        )

    @app.tool()
    def set_tag_schema(
        tag: str,
        schema: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return _serialize_events(registry.handle(SetTagSchema(tag=tag, schema=schema)))

    @app.tool()
    def sweep_stale_capabilities(threshold_days: int = 14) -> dict[str, Any]:
        return _serialize(
            registry.sweep_stale_capabilities(threshold_days=threshold_days)
        )

    # -- Discovery -------------------------------------------------------------

    @app.tool()
    def find_capable(
        tags: list[str],
        mode: str = "all",
    ) -> list[dict[str, Any]]:
        return [_serialize(c) for c in registry.find_capable(tags=tags, mode=mode)]

    @app.tool()
    def find_induced_by(morphogen_id: str) -> list[dict[str, Any]]:
        return [
            _serialize(c) for c in registry.find_induced_by(morphogen_id=morphogen_id)
        ]

    @app.tool()
    def get_tag_schema(tag: str) -> dict[str, Any] | None:
        return registry.get_tag_schema(name=tag)

    # -- Infrastructure --------------------------------------------------------

    def _status() -> dict[str, Any]:
        return {
            "ok": True,
            "db_path": db_path,
            "cell_count": len(registry.list_cells()),
            "tag_count": len(registry.list_tags()),
            "binding_count": len(registry.list_capabilities()),
        }

    @app.tool()
    def health() -> dict[str, Any]:
        return _status()

    @app.tool()
    def ensure_registry() -> dict[str, Any]:
        """Idempotent: schema is initialised at connect time; this tool
        confirms the registry is up and returns current counts."""
        return _status()

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the atlas MCP server.")
    parser.add_argument("--db", default="./atlas.db", help="SQLite database path.")
    parser.add_argument(
        "--transport",
        choices=("http", "stdio"),
        default="stdio",
        help="MCP transport to use.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host.")
    parser.add_argument("--port", type=int, default=8484, help="HTTP bind port.")
    args = parser.parse_args()

    app = create_app(db_path=args.db)
    if args.transport == "stdio":
        app.run(transport="stdio")
        return
    app.run(transport="http", host=args.host, port=args.port)


def _serialize_events(events: list[Any]) -> list[dict[str, Any]]:
    return [_serialize(event) for event in events]


def _serialize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(cast(Any, value))
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


if __name__ == "__main__":
    main()
