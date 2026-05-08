# State — atlas

This file is **operational truth**. What this cell currently runs,
exposes, depends on, and stores. Keep it accurate; update it in the
same PR as any change that affects what's live.

If a section is empty, leave the heading and write "Nothing yet."
The structure stays even when the content doesn't.

---

## What this cell does today

Registry of cells and their capabilities. Source of truth for which cells exist and what each can do, expressed as capability tags.

Nothing live yet — fill this in once the cell ships its first
real artifact.

---

## What's running

Atlas service is not implemented yet — no MCP server is up.

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
  `list_capabilities`. Tag-admin and discovery operations land in
  PR 2c.

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

- Python  (managed via `uv`)
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
