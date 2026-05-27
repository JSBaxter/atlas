"""Dispatch/smoke tests for the atlas MCP server.

Mirrors the queue's test_server.py pattern: exercises ``create_app`` via
``app.call_tool`` to confirm each tool lifecycle dispatches end-to-end
(Python → FastMCP → Registry → SQLiteRepository → SQLite).
"""

from __future__ import annotations

import asyncio
from typing import Any

from atlas.server import create_app


def _sc(result: Any) -> Any:
    """Return ``structured_content``, asserting it is not None."""
    content = result.structured_content
    assert content is not None
    return content


def test_health_and_ensure_registry(tmp_path):
    db = tmp_path / "atlas.db"
    app = create_app(str(db))

    async def run():
        h = await app.call_tool("health", {})
        assert _sc(h)["ok"] is True
        assert _sc(h)["cell_count"] == 0

        e = await app.call_tool("ensure_registry", {})
        assert _sc(e)["ok"] is True

    asyncio.run(run())


def test_cell_lifecycle(tmp_path):
    db = tmp_path / "atlas.db"
    app = create_app(str(db))

    async def run():
        reg = await app.call_tool(
            "register_cell",
            {
                "name": "cytometer",
                "purpose": "SvelteKit web app",
                "repo_url": "https://github.com/JSBaxter/cytometer",
            },
        )
        event = _sc(reg)["result"][0]
        cell_id = event["cell"]["id"]
        assert event["cell"]["name"] == "cytometer"
        assert event["was_existing"] is False

        # idempotent re-register
        reg2 = await app.call_tool(
            "register_cell",
            {"name": "cytometer", "purpose": "SvelteKit web app"},
        )
        event2 = _sc(reg2)["result"][0]
        assert event2["was_existing"] is True
        assert event2["cell"]["id"] == cell_id

        # get cell (Optional return type → FastMCP wraps in {"result": ...})
        got = await app.call_tool("get_cell", {"cell_id": cell_id})
        assert _sc(got)["result"]["id"] == cell_id

        # set inactive
        await app.call_tool(
            "set_cell_status", {"cell_id": cell_id, "status": "inactive"}
        )

        # list shows inactive
        cells = await app.call_tool("list_cells", {"status": "inactive"})
        assert any(c["id"] == cell_id for c in _sc(cells)["result"])

    asyncio.run(run())


def test_capability_declarations(tmp_path):
    db = tmp_path / "atlas.db"
    app = create_app(str(db))

    async def run():
        reg = await app.call_tool(
            "register_cell",
            {"name": "scanner", "purpose": "static analysis"},
        )
        cell_id = _sc(reg)["result"][0]["cell"]["id"]

        # declare new tag — description required on first registration
        decl = await app.call_tool(
            "declare_capability",
            {
                "cell_id": cell_id,
                "tag": "analysis.static.python",
                "description": "Python static-analysis capability",
            },
        )
        ev = _sc(decl)["result"][0]
        assert ev["tag"]["name"] == "analysis.static.python"
        assert ev["tag_was_new"] is True

        # redeclare same tag — refreshes binding
        decl2 = await app.call_tool(
            "declare_capability",
            {"cell_id": cell_id, "tag": "analysis.static.python"},
        )
        ev2 = _sc(decl2)["result"][0]
        assert ev2["tag_was_new"] is False

        # list capabilities
        caps = await app.call_tool("list_capabilities", {"cell_id": cell_id})
        assert len(_sc(caps)["result"]) == 1

        # refresh
        ref = await app.call_tool("refresh_capabilities", {"cell_id": cell_id})
        assert _sc(ref)["result"][0]["refreshed_count"] == 1

        # revoke
        rev = await app.call_tool(
            "revoke_capability",
            {"cell_id": cell_id, "tag": "analysis.static.python"},
        )
        assert _sc(rev)["result"][0]["was_present"] is True

        # revoke again — idempotent
        rev2 = await app.call_tool(
            "revoke_capability",
            {"cell_id": cell_id, "tag": "analysis.static.python"},
        )
        assert _sc(rev2)["result"][0]["was_present"] is False

    asyncio.run(run())


def test_tag_admin(tmp_path):
    db = tmp_path / "atlas.db"
    app = create_app(str(db))

    async def run():
        reg = await app.call_tool(
            "register_cell", {"name": "auditor", "purpose": "audit"}
        )
        cell_id = _sc(reg)["result"][0]["cell"]["id"]

        await app.call_tool(
            "declare_capability",
            {"cell_id": cell_id, "tag": "sast", "description": "SAST scanning"},
        )
        await app.call_tool(
            "declare_capability",
            {
                "cell_id": cell_id,
                "tag": "static-analysis",
                "description": "Static analysis",
            },
        )

        # list tags
        tags = await app.call_tool("list_tags", {})
        names = {t["tag"]["name"] for t in _sc(tags)["result"]}
        assert "sast" in names and "static-analysis" in names

        # set tag schema
        schema = {"type": "object", "properties": {"severity": {"type": "string"}}}
        st = await app.call_tool("set_tag_schema", {"tag": "sast", "schema": schema})
        assert _sc(st)["result"][0]["tag"]["payload_schema"] == schema

        # get tag schema (Optional return type → FastMCP wraps in {"result": ...})
        got = await app.call_tool("get_tag_schema", {"tag": "sast"})
        assert _sc(got)["result"] == schema

        # deprecate with alias
        dep = await app.call_tool(
            "deprecate_tag", {"tag": "sast", "alias_to": "static-analysis"}
        )
        assert _sc(dep)["result"][0]["tag"]["status"] == "deprecated"
        assert _sc(dep)["result"][0]["tag"]["alias_to"] == "static-analysis"

        # propose alias
        await app.call_tool(
            "declare_capability",
            {"cell_id": cell_id, "tag": "linting", "description": "Linting"},
        )
        al = await app.call_tool(
            "propose_alias",
            {"deprecated": "linting", "canonical": "static-analysis"},
        )
        assert _sc(al)["result"][0]["tag"]["alias_to"] == "static-analysis"

    asyncio.run(run())


def test_discovery(tmp_path):
    db = tmp_path / "atlas.db"
    app = create_app(str(db))

    async def run():
        r1 = await app.call_tool(
            "register_cell", {"name": "alpha", "purpose": "alpha cell"}
        )
        r2 = await app.call_tool(
            "register_cell",
            {
                "name": "beta",
                "purpose": "beta cell",
                "induced_by": "morphogen_abc",
            },
        )
        alpha_id = _sc(r1)["result"][0]["cell"]["id"]
        beta_id = _sc(r2)["result"][0]["cell"]["id"]

        await app.call_tool(
            "declare_capability",
            {"cell_id": alpha_id, "tag": "analysis", "description": "analysis root"},
        )
        await app.call_tool(
            "declare_capability",
            {
                "cell_id": alpha_id,
                "tag": "analysis.static",
                "description": "static analysis",
            },
        )
        await app.call_tool(
            "declare_capability",
            {"cell_id": beta_id, "tag": "analysis", "description": "analysis root"},
        )

        # find_capable — mode=all
        fc = await app.call_tool("find_capable", {"tags": ["analysis"], "mode": "all"})
        names = {c["name"] for c in _sc(fc)["result"]}
        assert names == {"alpha", "beta"}

        # prefix match: querying "analysis.static" finds alpha which also has "analysis"
        fc2 = await app.call_tool(
            "find_capable", {"tags": ["analysis.static"], "mode": "all"}
        )
        names2 = {c["name"] for c in _sc(fc2)["result"]}
        assert "alpha" in names2

        # find_induced_by
        fi = await app.call_tool("find_induced_by", {"morphogen_id": "morphogen_abc"})
        assert _sc(fi)["result"][0]["name"] == "beta"

        # spawn-race conflict — second register_cell with same induced_by
        conflict = await app.call_tool(
            "register_cell",
            {
                "name": "gamma",
                "purpose": "duplicate",
                "induced_by": "morphogen_abc",
            },
        )
        ev = _sc(conflict)["result"][0]
        # CellInductionConflict event returned instead of CellRegistered
        assert "existing_cell" in ev
        assert ev["induced_by"] == "morphogen_abc"

    asyncio.run(run())


def test_sweep_stale_capabilities(tmp_path):
    db = tmp_path / "atlas.db"
    app = create_app(str(db))

    async def run():
        reg = await app.call_tool(
            "register_cell", {"name": "old", "purpose": "old cell"}
        )
        cell_id = _sc(reg)["result"][0]["cell"]["id"]
        await app.call_tool(
            "declare_capability",
            {"cell_id": cell_id, "tag": "legacy", "description": "legacy tag"},
        )

        # Sweep with threshold_days=0 — everything is immediately stale
        sweep = await app.call_tool("sweep_stale_capabilities", {"threshold_days": 0})
        report = _sc(sweep)
        assert report["threshold_days"] == 0
        assert len(report["stale_bindings"]) == 1
        assert report["stale_bindings"][0]["tag"] == "legacy"

    asyncio.run(run())
