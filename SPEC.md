# atlas — design spec

> **Status**: pre-implementation. Written before the `atlas` cell has been spawned. When it is, this document moves into the cell as `SPEC.md` (and this file is deleted). Until then it lives at `cells/_designs/atlas.md`.

## Purpose

Atlas is the colony's registry of cells and their capabilities. It holds:

- Which cells exist (name, purpose, repo URL, status)
- What each cell can do, expressed as capability **tags** (e.g. `static-analysis`, `analysis.static.python`)
- The controlled vocabulary of tags themselves — what's registered, what's deprecated, what's an alias for what

It is *the* source of truth for two questions: "What cells are there?" and "Which cells can do X?"

It does **not** mediate communication or feature requests between cells — that's `morphogen`'s job. Atlas is read-mostly, declarative.

## Naming

After the [Human Cell Atlas](https://www.humancellatlas.org/) — a real biology project that catalogues cell types and their properties.

## Position in the colony

Atlas is foundational: it depends on no other cell, and many other cells (notably morphogen) consume it. It is itself a cell — one repo, one purpose, one queue, scaffolded from `stem-cell`.

**Cross-cell architecture note**: MCP servers don't call each other directly — the agent is the bus. Atlas exposes lookup tools (`find_capable`, `list_tags`); cells/agents call atlas to learn the colony state, then act on what they learn. Morphogen does *not* call atlas at runtime; capability matching happens at read time against morphogen's own storage, with the reader cell passing in its own declared tags.

## Design decisions

1. **Tag shape** — kebab-case strings, optional dot hierarchy for opt-in structure. No per-cell namespacing; tags are global.
2. **Self-declaration** — cells declare their own tags via MCP calls. Operator does not manually attach tags. Cells know what they do; atlas catalogs.
3. **Auto-register-with-suggestion** — new tags are auto-registered, but atlas runs a similarity check (string distance + word overlap) and returns close matches. Caller chooses whether to use the existing tag or insist on the new one. Friction kills adoption; the fragmentation cost is borne by the proposer at decide time.
4. **No hard delete** — tags are deprecated, not removed. Aliases (operator-managed, one-way) keep references valid.
5. **Heartbeat** — cells re-declare capabilities weekly. Stale bindings (no refresh in 14 days) get marked stale and excluded from discovery. Catches dead cells naturally.
6. **Default match mode = `all`** — when filtering by multiple tags, default narrows (AND). Override via explicit `mode="any"`.
7. **Implicit prefix matching** — a tag matches its ancestors and descendants in the dot hierarchy in *both* directions. No wildcard syntax. `analysis` matches `analysis.static.python` and vice versa.
8. **Description required at first registration** — registry stays self-documenting.

## MCP tool surface (~10 tools)

```
Capability declarations (called by cells):
  declare_capability(cell, tag, description?) -> {registered, suggestion?}
    # description required only at tag's first-ever registration
    # suggestion field returns close matches for fragmentation prevention
  revoke_capability(cell, tag)
  refresh_capabilities(cell)
    # heartbeat — bumps last_refreshed_at on all of cell's bindings
  list_capabilities(cell?) -> [(cell, tag, declared_at, last_refreshed_at), ...]

Registry admin (operator-facing):
  list_tags(status?) -> [(tag, description, status, alias_to?, usage_count), ...]
  deprecate_tag(tag, alias_to=?)
  propose_alias(deprecated, canonical)
  sweep_stale_capabilities(threshold_days=14)
    # marks bindings not refreshed in N days as stale; cron-able

Discovery (called by cells/agents):
  find_capable(tags=[...], mode="all") -> [cell, ...]
    # default mode=all; implicit prefix match (both directions in the dot tree)
    # alias resolution applied transparently
    # excludes stale bindings and inactive cells

Infrastructure:
  health
  ensure_registry
```

## SQLite schema

```sql
CREATE TABLE cells (
  id            TEXT PRIMARY KEY,         -- generated, e.g. "cyt_a4f"
  name          TEXT UNIQUE NOT NULL,     -- "cytometer"
  purpose       TEXT NOT NULL,
  repo_url      TEXT,
  registered_at TIMESTAMP NOT NULL,
  status        TEXT NOT NULL DEFAULT 'active'  -- active | inactive
);

CREATE TABLE tags (
  name           TEXT PRIMARY KEY,        -- "static-analysis"
  description    TEXT NOT NULL,           -- required at first registration
  status         TEXT NOT NULL DEFAULT 'active',  -- active | deprecated
  alias_to       TEXT REFERENCES tags(name),      -- nullable
  registered_at  TIMESTAMP NOT NULL,
  registered_by  TEXT NOT NULL REFERENCES cells(id)
);

CREATE TABLE capability_bindings (
  cell_id            TEXT NOT NULL REFERENCES cells(id),
  tag                TEXT NOT NULL REFERENCES tags(name),
  declared_at        TIMESTAMP NOT NULL,
  last_refreshed_at  TIMESTAMP NOT NULL,
  PRIMARY KEY (cell_id, tag)
);

CREATE INDEX idx_bindings_tag       ON capability_bindings(tag);
CREATE INDEX idx_bindings_refreshed ON capability_bindings(last_refreshed_at);
CREATE INDEX idx_tags_status        ON tags(status);
```

## Lifecycle

### Tag lifecycle
- `active`: in use, can be declared and matched
- `deprecated`: no longer canonical; if `alias_to` is set, references resolve transparently to the canonical tag at lookup time

### Capability binding lifecycle
- Bindings track `(cell, tag, declared_at, last_refreshed_at)`
- `refresh_capabilities` extends `last_refreshed_at` on all of a cell's bindings to now
- Bindings with `last_refreshed_at < now - threshold_days` are stale; excluded from `find_capable`
- Stale bindings remain in the table for audit (no hard delete)

### Cell lifecycle
- `active`: discoverable, capabilities matched
- `inactive`: not discoverable but record retained

## Open questions

1. **Similarity threshold for fragmentation suggestions** — needs tuning during early use. Start permissive (return suggestions on any non-trivial overlap), tighten if signal-to-noise is bad.
2. **Whether `find_capable` should ever expose `inactive` cells** — probably no, but a flag for archaeological queries (`include_inactive=true`) might be useful for operator tools.
3. **Cell-proposed aliases** — currently aliases are operator-managed only. Should cells be able to propose aliases for their own capabilities (`I declare 'sast' and 'static-analysis' are equivalent`)? Loosening this is a follow-up question — keep operator-only at first.
4. **Rate limiting on `declare_capability`** — probably not needed at colony scale, but worth noting. A cell that calls it 1000 times in a minute is buggy; reject above some sane threshold.
