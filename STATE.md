# State — atlas

This file is **operational truth**. What this cell currently runs,
exposes, depends on, and stores. Keep it accurate; update it in the
same PR as any change that affects what's live.

If a section is empty, leave the heading and write "Nothing yet."
The structure stays even when the content doesn't.

---

## What this cell does today

Registry of cells and their capabilities. Source of truth for which cells exist and what each can do, expressed as capability tags.

The atlas MCP server (`src/atlas/server.py`) exposes 16 tools covering cell lifecycle, capability declarations, tag administration, discovery, and infrastructure. Other cells and agents call it to register, declare, and look up capabilities.

---

## What's running

**Atlas MCP server** (`src/atlas/server.py`):
- Transport: stdio (for MCP client integration)
- Entry point: `uv run atlas --transport stdio` (registered in `.mcp.json`)
- Storage: SQLite at `./atlas.db` (path configurable via `--db`)
- 16 tools: cell lifecycle (`register_cell`, `set_cell_status`, `get_cell`,
  `list_cells`), capability declarations (`declare_capability`,
  `revoke_capability`, `refresh_capabilities`, `list_capabilities`), registry
  admin (`list_tags`, `deprecate_tag`, `propose_alias`, `set_tag_schema`,
  `sweep_stale_capabilities`), discovery (`find_capable`, `find_induced_by`,
  `get_tag_schema`), infrastructure (`health`, `ensure_registry`)
- Similarity for fragmentation prevention: rapidfuzz `token_set_ratio`, ≥ 70
  score threshold, up to 5 suggestions

Operational infrastructure that **is** live for this cell:

- **Bot identity**: `jb-colony-bot` (GitHub App, ID `3638446`,
  install `130427381`). Credentials at `~/.config/colony-bot/`
  on the operator workstation. Used via
  `dev-tools/agent-bot/as-bot.sh` (set
  `AGENT_BOT_CRED_DIR=~/.config/colony-bot/`).
- **Branch protection on `main`**: requires a PR with at least one
  approving review (operator approves bot's PRs); dismisses stale
  reviews on push; no force pushes; no deletions.
- **Cell-root Python project**: `pyproject.toml` at repo root,
  package skeleton at `src/atlas/`, tests at `tests/`. Managed via
  `uv`. Toolchain: `ruff` (format + lint), `ty` (type check),
  `pytest`. Pre-commit hooks gate atlas changes locally; CI
  (`.github/workflows/quality.yml`) does **not** yet run the atlas
  job — adding it is blocked by the bot lacking the GitHub App
  `workflows` permission. Follow-up needed.
- **Domain layer foundation** (`src/atlas/domain/`): models
  (`Cell`, `Tag`, `CapabilityBinding`), `AtlasRepository` Protocol,
  `Registry` service with command/event dispatch. Cell-lifecycle
  operations live (`register_cell` with idempotence + induced_by
  spawn-race protection, `set_cell_status`, `get_cell`,
  `list_cells`). Storage-agnostic — backed by an in-memory test
  fixture only (no SQLite yet).
- **Capability declarations** (also in `src/atlas/domain/`):
  `declare_capability` (auto-registers tag on first declare;
  description required at first registration; suggestion field
  plumbed through but stubbed at `[]`), `revoke_capability` (hard
  delete; tag survives), `refresh_capabilities` (heartbeat —
  bumps `last_refreshed_at` on all of a cell's bindings),
  `list_capabilities`.
- **Tag admin** (also in `src/atlas/domain/`): `deprecate_tag`
  (with optional `alias_to`), `propose_alias` (operator-managed
  one-hop redirect; canonical must be active),
  `set_tag_schema` (attach optional JSON payload schema;
  opaque to atlas), `list_tags` (returns `TagListing` with
  per-tag `usage_count`), `get_tag_schema`.
- **Discovery** (also in `src/atlas/domain/`): `find_capable`
  (implicit dot-hierarchy prefix matching in both directions,
  alias resolution forward AND reverse, stale exclusion via
  14-day threshold, inactive-cell exclusion; modes `all` /
  `any`), `find_induced_by` (lookup by morphogen pointer; 0 or 1
  cells), `sweep_stale_capabilities` (observational
  `StaleBindingsReport`; no mutation).
- **SQLite repository** (`src/atlas/infra/`): `SQLiteRepository`
  implements every `AtlasRepository` method. Schema lives in
  `schema.sql` per SPEC's tables (cells with unique `induced_by`
  index, tags with self-referential `alias_to` FK, bindings with
  composite PK and refresh-time index). `payload_schema`
  serialized as JSON text. `SQLiteRepository.connect(path)` is
  the connect-and-init helper. The Registry is repository-agnostic
  — wiring it against SQLite is a one-line change at
  construction. PR 4 wires the MCP server on top.

Examples of what will belong here once the cell ships its service:

- A service or daemon, with where it runs and the address it's
  reachable at
- A scheduled job, with the schedule and the system that runs it
- A library, with its current released version and where it's
  published
- A CLI, with where it's installed and its current version

---

## Dependencies

### Build / runtime

- Python (managed via `uv`; package = true, build backend = `uv_build`)
- `fastmcp>=2.0` — MCP server framework
- `rapidfuzz>=3.0` — tag similarity (fragmentation prevention)
- The bundled queue runtime under `dev-tools/queue/` brings its own
  Python project
### External

Nothing yet.

---

## Where secrets live

Secrets are **never** committed. Possible homes:

- A password manager (1Password, Bitwarden, etc.) — operator
  workstation only
- An environment variable on the deployment target
- A secret store the cell explicitly authenticates against

When the cell starts using a secret, list it here with its source
(not its value):

```
| Secret              | Source                                    |
|---------------------|-------------------------------------------|
| GITHUB_TOKEN        | Operator's gh CLI auth                    |
| ...                 | ...                                       |
```

---

## What's NOT under this cell's control

- Anything outside this repo
- Anything the operator runs on their own machine and hasn't
  committed here

---

## Drift log

When `STATE.md` doesn't match reality and the discrepancy can't be
fixed inline, log it here with a date and a tracked task ID:

```
- 2026-MM-DD — <description> — task_xxxxxx
```

(Empty until something drifts.)
