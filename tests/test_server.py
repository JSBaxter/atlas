"""Dispatch/smoke tests for the atlas MCP server.

Mirrors the queue's test_server.py pattern: exercises ``create_app`` via
``app.call_tool`` to confirm each tool lifecycle dispatches end-to-end
(Python → FastMCP → Registry → SQLiteRepository → SQLite).

Coverage target: every tool exercised for its happy path, optional-parameter
variants, idempotence, and None/empty return cases.
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


# ---------------------------------------------------------------------------
# Additional coverage: edge cases, parameter variants, None/empty returns
# ---------------------------------------------------------------------------


def test_get_cell_returns_none_for_unknown_id(tmp_path):
    app = create_app(str(tmp_path / "atlas.db"))

    async def run():
        result = await app.call_tool("get_cell", {"cell_id": "nonexistent-id"})
        assert _sc(result)["result"] is None

    asyncio.run(run())


def test_list_cells_unfiltered_returns_all(tmp_path):
    app = create_app(str(tmp_path / "atlas.db"))

    async def run():
        r1 = await app.call_tool("register_cell", {"name": "a", "purpose": "p"})
        r2 = await app.call_tool("register_cell", {"name": "b", "purpose": "p"})
        a_id = _sc(r1)["result"][0]["cell"]["id"]
        b_id = _sc(r2)["result"][0]["cell"]["id"]
        await app.call_tool("set_cell_status", {"cell_id": b_id, "status": "inactive"})

        cells = await app.call_tool("list_cells", {})
        ids = {c["id"] for c in _sc(cells)["result"]}
        assert a_id in ids and b_id in ids

    asyncio.run(run())


def test_list_cells_empty_database(tmp_path):
    app = create_app(str(tmp_path / "atlas.db"))

    async def run():
        cells = await app.call_tool("list_cells", {})
        assert _sc(cells)["result"] == []

    asyncio.run(run())


def test_set_cell_status_round_trip(tmp_path):
    app = create_app(str(tmp_path / "atlas.db"))

    async def run():
        reg = await app.call_tool("register_cell", {"name": "ping", "purpose": "p"})
        cell_id = _sc(reg)["result"][0]["cell"]["id"]

        await app.call_tool(
            "set_cell_status", {"cell_id": cell_id, "status": "inactive"}
        )
        inactive = await app.call_tool("list_cells", {"status": "inactive"})
        assert any(c["id"] == cell_id for c in _sc(inactive)["result"])

        await app.call_tool("set_cell_status", {"cell_id": cell_id, "status": "active"})
        active = await app.call_tool("list_cells", {"status": "active"})
        assert any(c["id"] == cell_id for c in _sc(active)["result"])

    asyncio.run(run())


def test_register_cell_with_repo_url(tmp_path):
    app = create_app(str(tmp_path / "atlas.db"))

    async def run():
        reg = await app.call_tool(
            "register_cell",
            {
                "name": "repo-cell",
                "purpose": "has a repo",
                "repo_url": "https://github.com/JSBaxter/repo-cell",
            },
        )
        ev = _sc(reg)["result"][0]
        assert ev["cell"]["repo_url"] == "https://github.com/JSBaxter/repo-cell"

    asyncio.run(run())


def test_list_capabilities_global_view(tmp_path):
    app = create_app(str(tmp_path / "atlas.db"))

    async def run():
        r1 = await app.call_tool("register_cell", {"name": "c1", "purpose": "p"})
        r2 = await app.call_tool("register_cell", {"name": "c2", "purpose": "p"})
        c1 = _sc(r1)["result"][0]["cell"]["id"]
        c2 = _sc(r2)["result"][0]["cell"]["id"]
        await app.call_tool(
            "declare_capability", {"cell_id": c1, "tag": "foo", "description": "foo"}
        )
        await app.call_tool(
            "declare_capability", {"cell_id": c2, "tag": "bar", "description": "bar"}
        )

        # No cell_id filter → all capabilities returned
        caps = await app.call_tool("list_capabilities", {})
        tags = {b["tag"] for b in _sc(caps)["result"]}
        assert "foo" in tags and "bar" in tags

    asyncio.run(run())


def test_list_capabilities_empty(tmp_path):
    app = create_app(str(tmp_path / "atlas.db"))

    async def run():
        reg = await app.call_tool("register_cell", {"name": "empty", "purpose": "p"})
        cell_id = _sc(reg)["result"][0]["cell"]["id"]
        caps = await app.call_tool("list_capabilities", {"cell_id": cell_id})
        assert _sc(caps)["result"] == []

    asyncio.run(run())


def test_list_tags_with_status_filter(tmp_path):
    app = create_app(str(tmp_path / "atlas.db"))

    async def run():
        reg = await app.call_tool("register_cell", {"name": "tagger", "purpose": "p"})
        cell_id = _sc(reg)["result"][0]["cell"]["id"]
        await app.call_tool(
            "declare_capability",
            {"cell_id": cell_id, "tag": "active-tag", "description": "a"},
        )
        await app.call_tool(
            "declare_capability",
            {"cell_id": cell_id, "tag": "old-tag", "description": "o"},
        )
        await app.call_tool("deprecate_tag", {"tag": "old-tag"})

        active_tags = await app.call_tool("list_tags", {"status": "active"})
        active_names = {t["tag"]["name"] for t in _sc(active_tags)["result"]}
        assert "active-tag" in active_names
        assert "old-tag" not in active_names

        deprecated_tags = await app.call_tool("list_tags", {"status": "deprecated"})
        deprecated_names = {t["tag"]["name"] for t in _sc(deprecated_tags)["result"]}
        assert "old-tag" in deprecated_names
        assert "active-tag" not in deprecated_names

    asyncio.run(run())


def test_list_tags_empty(tmp_path):
    app = create_app(str(tmp_path / "atlas.db"))

    async def run():
        tags = await app.call_tool("list_tags", {})
        assert _sc(tags)["result"] == []

    asyncio.run(run())


def test_deprecate_tag_without_alias(tmp_path):
    app = create_app(str(tmp_path / "atlas.db"))

    async def run():
        reg = await app.call_tool("register_cell", {"name": "dep-cell", "purpose": "p"})
        cell_id = _sc(reg)["result"][0]["cell"]["id"]
        await app.call_tool(
            "declare_capability",
            {"cell_id": cell_id, "tag": "old", "description": "old"},
        )

        dep = await app.call_tool("deprecate_tag", {"tag": "old"})
        ev = _sc(dep)["result"][0]
        assert ev["tag"]["status"] == "deprecated"
        assert ev["tag"]["alias_to"] is None

    asyncio.run(run())


def test_set_tag_schema_clear_with_none(tmp_path):
    app = create_app(str(tmp_path / "atlas.db"))

    async def run():
        reg = await app.call_tool("register_cell", {"name": "schemer", "purpose": "p"})
        cell_id = _sc(reg)["result"][0]["cell"]["id"]
        await app.call_tool(
            "declare_capability",
            {"cell_id": cell_id, "tag": "typed", "description": "t"},
        )

        schema = {"type": "object"}
        await app.call_tool("set_tag_schema", {"tag": "typed", "schema": schema})
        got = await app.call_tool("get_tag_schema", {"tag": "typed"})
        assert _sc(got)["result"] == schema

        # Clear the schema
        await app.call_tool("set_tag_schema", {"tag": "typed", "schema": None})
        cleared = await app.call_tool("get_tag_schema", {"tag": "typed"})
        assert _sc(cleared)["result"] is None

    asyncio.run(run())


def test_get_tag_schema_returns_none_for_unknown_tag(tmp_path):
    app = create_app(str(tmp_path / "atlas.db"))

    async def run():
        result = await app.call_tool("get_tag_schema", {"tag": "no-such-tag"})
        assert _sc(result)["result"] is None

    asyncio.run(run())


def test_get_tag_schema_returns_none_when_no_schema_set(tmp_path):
    app = create_app(str(tmp_path / "atlas.db"))

    async def run():
        reg = await app.call_tool("register_cell", {"name": "bare", "purpose": "p"})
        cell_id = _sc(reg)["result"][0]["cell"]["id"]
        await app.call_tool(
            "declare_capability",
            {"cell_id": cell_id, "tag": "no-schema", "description": "n"},
        )
        result = await app.call_tool("get_tag_schema", {"tag": "no-schema"})
        assert _sc(result)["result"] is None

    asyncio.run(run())


def test_find_capable_mode_any(tmp_path):
    app = create_app(str(tmp_path / "atlas.db"))

    async def run():
        r1 = await app.call_tool("register_cell", {"name": "x", "purpose": "p"})
        r2 = await app.call_tool("register_cell", {"name": "y", "purpose": "p"})
        x_id = _sc(r1)["result"][0]["cell"]["id"]
        y_id = _sc(r2)["result"][0]["cell"]["id"]

        await app.call_tool(
            "declare_capability", {"cell_id": x_id, "tag": "cap.a", "description": "a"}
        )
        await app.call_tool(
            "declare_capability", {"cell_id": y_id, "tag": "cap.b", "description": "b"}
        )

        # mode=any: each cell matches at least one tag
        fc = await app.call_tool(
            "find_capable", {"tags": ["cap.a", "cap.b"], "mode": "any"}
        )
        names = {c["name"] for c in _sc(fc)["result"]}
        assert "x" in names and "y" in names

        # mode=all: only a cell with BOTH tags matches → neither qualifies
        fc_all = await app.call_tool(
            "find_capable", {"tags": ["cap.a", "cap.b"], "mode": "all"}
        )
        assert _sc(fc_all)["result"] == []

    asyncio.run(run())


def test_find_capable_returns_empty_when_no_match(tmp_path):
    app = create_app(str(tmp_path / "atlas.db"))

    async def run():
        result = await app.call_tool("find_capable", {"tags": ["nonexistent.tag"]})
        assert _sc(result)["result"] == []

    asyncio.run(run())


def test_find_induced_by_returns_empty_when_no_match(tmp_path):
    app = create_app(str(tmp_path / "atlas.db"))

    async def run():
        result = await app.call_tool(
            "find_induced_by", {"morphogen_id": "no-such-morphogen"}
        )
        assert _sc(result)["result"] == []

    asyncio.run(run())


def test_health_counts_reflect_state(tmp_path):
    app = create_app(str(tmp_path / "atlas.db"))

    async def run():
        h0 = await app.call_tool("health", {})
        assert _sc(h0)["cell_count"] == 0
        assert _sc(h0)["tag_count"] == 0
        assert _sc(h0)["binding_count"] == 0

        reg = await app.call_tool("register_cell", {"name": "counter", "purpose": "p"})
        cell_id = _sc(reg)["result"][0]["cell"]["id"]
        await app.call_tool(
            "declare_capability",
            {"cell_id": cell_id, "tag": "metrics", "description": "m"},
        )

        h1 = await app.call_tool("health", {})
        assert _sc(h1)["cell_count"] == 1
        assert _sc(h1)["tag_count"] == 1
        assert _sc(h1)["binding_count"] == 1

    asyncio.run(run())


def test_ensure_registry_counts_match_health(tmp_path):
    app = create_app(str(tmp_path / "atlas.db"))

    async def run():
        reg = await app.call_tool("register_cell", {"name": "ensured", "purpose": "p"})
        cell_id = _sc(reg)["result"][0]["cell"]["id"]
        await app.call_tool(
            "declare_capability",
            {"cell_id": cell_id, "tag": "signal", "description": "s"},
        )

        h = await app.call_tool("health", {})
        e = await app.call_tool("ensure_registry", {})
        assert _sc(e)["cell_count"] == _sc(h)["cell_count"]
        assert _sc(e)["tag_count"] == _sc(h)["tag_count"]
        assert _sc(e)["binding_count"] == _sc(h)["binding_count"]

    asyncio.run(run())


def test_refresh_capabilities_on_empty_cell(tmp_path):
    app = create_app(str(tmp_path / "atlas.db"))

    async def run():
        reg = await app.call_tool("register_cell", {"name": "bare2", "purpose": "p"})
        cell_id = _sc(reg)["result"][0]["cell"]["id"]

        ref = await app.call_tool("refresh_capabilities", {"cell_id": cell_id})
        assert _sc(ref)["result"][0]["refreshed_count"] == 0

    asyncio.run(run())


def test_sweep_stale_capabilities_empty_returns_no_stale(tmp_path):
    app = create_app(str(tmp_path / "atlas.db"))

    async def run():
        sweep = await app.call_tool("sweep_stale_capabilities", {"threshold_days": 0})
        report = _sc(sweep)
        assert report["stale_bindings"] == []

    asyncio.run(run())
