# Handoff — implement atlas

> **This file is transient.** It briefs the next agent that picks up the atlas implementation. Delete it as part of the same PR that lands the first real feature. Once `STATE.md` reflects "atlas service running", this doc rots.

You're inheriting **atlas**, a fresh agent cell at `~/Documents/repos/cells/atlas/`. Purpose: the colony's registry of cells and their capabilities — source of truth for "what cells are there?" and "which cells can do X?". Full spec is at [`SPEC.md`](./SPEC.md). **Read it first.**

## What's already been done

- Cell scaffolded from [`stem-cell`](https://github.com/JSBaxter/stem-cell) at commit `d2d0c27` via `gh:JSBaxter/stem-cell` URL form (proper reproducible spawn — `.copier-answers.yml` is canonical).
- Pushed to GitHub: https://github.com/JSBaxter/atlas (public, `main` tracks `origin/main`).
- Queue verified: `uv sync --directory dev-tools/queue && uv run --directory dev-tools/queue pytest` → 85/85 pass.
- Python toolchain pre-wired by template: `.pre-commit-config.yaml`, `.yamllint.yml`, `.github/workflows/` for CI, ruff + mypy configs.
- Commits on `main`: initial scaffold, queue lockfile pinned, this handoff + SPEC.md import.

## Decisions already made

The full design is locked in [`SPEC.md`](./SPEC.md). In particular:

- **Tag shape**: kebab-case strings, optional dot hierarchy, no per-cell namespacing.
- **Self-declaration**: cells declare their own tags via MCP; operator does not.
- **Auto-register-with-suggestion**: new tags auto-register but atlas runs a similarity check and returns close matches for fragmentation prevention.
- **Heartbeat at weekly cadence**, stale at 14 days.
- **Default match mode = `all`**, implicit prefix matching in both directions.
- **Description required at first registration** of a tag.
- **No hard delete**: tags deprecated, not removed; aliases are operator-managed.
- **MCP tool surface (~10)** and **3-table SQLite schema** are spec'd in full.

## Decisions still yours

1. **Cell-root Python project layout.** The template gave us ruff/mypy/CI but no `pyproject.toml` at the cell root yet. The atlas service is the cell's primary purpose, so it lives outside `dev-tools/`. Suggested: `pyproject.toml` at root, package at `src/atlas/`, MCP entry at `src/atlas/server.py` mirroring the queue's `dev-tools/queue/server.py` pattern.
2. **Implementation breakdown.** One big PR or several smaller ones (domain → infra → server → MCP tools)? I'd lean several smaller — the queue cell has clean separation between `domain/`, `infra/`, and `server.py` and that's a good pattern to mirror.
3. **`.mcp.json` registration.** Currently only the queue is wired. Once the atlas MCP server exists and runs locally, register it alongside queue so operator can interact with atlas from inside this cell's Claude sessions for testing.
4. **Similarity algorithm for `declare_capability`'s suggestion field.** Spec says "string distance + word overlap" but doesn't pick one. Reasonable choices: rapidfuzz token ratio, or simpler Levenshtein on normalized strings. Pick one, record rationale in the queue.

## Plan

1. **Read the cell.** `CLAUDE.md` auto-loads — follow its reading order (MANIFESTO → CONTRIBUTING → TESTING → STATE → README). Then `SPEC.md` cover-to-cover. Then skim `dev-tools/queue/` (especially `domain/`, `infra/repository.py`, `server.py`) — that's the architectural pattern to mirror.
2. **Queue handshake** via the queue MCP server (registered in `.mcp.json`):
   - `health` to verify
   - `add_idea` (title: "implement atlas registry — first cut")
   - `scope_task` → `claim_task` → `open_session`
   - `add_note` recording your decisions on the four open items above.
3. **Branch** per CONTRIBUTING.md naming. Suggested first branch: `feat/bootstrap-python-project` to set up `pyproject.toml`, `src/atlas/` skeleton, and a passing `pytest` from the cell root. Keep this PR small — just the toolchain bones, no feature code.
4. **Subsequent branches** (one PR each, in order):
   - `feat/atlas-domain-layer` — models (`Cell`, `Tag`, `CapabilityBinding`), service contracts, in-memory repository for testing, full test coverage of business logic.
   - `feat/atlas-sqlite-repository` — `infra/` mirroring the queue's pattern, schema migrations.
   - `feat/atlas-mcp-server` — wire the ~10 tools as MCP, register in `.mcp.json`.
   - `chore/atlas-state-md` — update `STATE.md` to reflect atlas running locally, delete this `HANDOFF.md`.
5. **Per CONTRIBUTING.md**: every PR references the queue task ID. Self-approval is fine. Squash-merge default. `complete_task` only after merge to main.

## Constraints

- **Don't touch `dev-tools/queue/`** — Python, self-contained, ships its own uv venv, not your concern.
- **Atlas does not call other cells at runtime.** It's foundational; no outbound dependencies.
- **No event sourcing yet** — the spec specifies mutate-in-place storage with status fields. Resist the urge to over-engineer; add an event log later if observability demands it.
- **Don't implement morphogen here.** Morphogen is a separate cell; atlas just provides the vocabulary it consumes. The two cells share no code.
- **If a spec choice is wrong** (you discover it during implementation), don't silently work around it. Update `SPEC.md` as part of the PR that diverges, and explain why.

## References

- Spec: [`SPEC.md`](./SPEC.md)
- Template: https://github.com/JSBaxter/stem-cell (HEAD `d2d0c27`, pinned in `.copier-answers.yml`)
- Architectural reference for the cell pattern: `dev-tools/queue/` (especially `domain/`, `infra/repository.py`, `server.py`, `WORKFLOW.md`)
- Sister cells in the colony:
  - [`cytometer`](https://github.com/JSBaxter/cytometer) — different purpose, pre-bootstrap (JS toolchain pending in another session)
  - `morphogen` — not yet spawned; will consume atlas's tag vocabulary; spec lives at `cells/_designs/morphogen.md`
