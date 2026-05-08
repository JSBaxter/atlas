# atlas — design spec

> **Status**: pre-implementation. Living spec for the atlas cell — implement against this. Updates as design refinements emerge.

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
7. **Implicit prefix matching** — a tag matches its ancestors and descendants in the dot hierarchy in *both* directions. No wildcard syntax. `analysis` matches `analysis.static.python` and vice versa. Alias resolution applies in both directions too: querying a deprecated alias finds cells bound to its canonical, and querying the canonical also finds cells bound to deprecated aliases of it (the alias relation expresses semantic equivalence).
8. **Description required at first registration** — registry stays self-documenting.
9. **Optional payload schemas per tag** — registered tags can carry an optional JSON schema (`tags.payload_schema`) describing the expected shape of payloads emitted against them. Cells fetch the schema (`get_tag_schema`) and normalize their payloads (strip extras, fill defaults) **before** emitting to morphogen. The bus boundary doesn't enforce schemas — discipline + tooling does. This is the lever that prevents trivial payload variations from fragmenting morphogen's concentration counter.
10. **Induction lineage tracked bidirectionally** — when a cell is spawned in response to a morphogen-induced need, the spawner registers it with `induced_by=<morphogen_id>`. Atlas enforces "at most one cell per `induced_by`" so spawn races resolve at register-time. `find_induced_by(morphogen_id)` answers "which cells came from which signals?" the other way. Note: `induced_by` is a free-form text pointer — atlas does not validate it against morphogen's storage (separate cells, separate DBs).

## MCP tool surface (~15 tools)

```
Cell lifecycle (called by cells on spawn):
  register_cell(name, purpose, repo_url, induced_by?) -> cell_id
    # idempotent on (name); returns existing cell_id if name already registered
    # induced_by enforces at-most-one-cell-per-morphogen for spawn-race protection
  set_cell_status(cell, status)        # active | inactive
  get_cell(cell) -> {id, name, purpose, repo_url, status, induced_by?, ...}

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
  set_tag_schema(tag, schema)
    # operator-only; attaches/updates optional payload schema for the tag
  sweep_stale_capabilities(threshold_days=14)
    # marks bindings not refreshed in N days as stale; cron-able

Discovery (called by cells/agents):
  find_capable(tags=[...], mode="all") -> [cell, ...]
    # default mode=all; implicit prefix match (both directions in the dot tree)
    # alias resolution applied transparently
    # excludes stale bindings and inactive cells
  find_induced_by(morphogen_id) -> [cell, ...]
    # which cell(s) were spawned in response to this morphogen
  get_tag_schema(tag) -> schema?
    # returns the optional payload schema attached to a tag, if any

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
  status        TEXT NOT NULL DEFAULT 'active', -- active | inactive
  induced_by    TEXT                            -- nullable; morphogen_id pointer
                                                -- (free-form, not FK validated)
);

-- At most one cell per morphogen-induced need (spawn race protection)
CREATE UNIQUE INDEX idx_cells_induced_by ON cells(induced_by) WHERE induced_by IS NOT NULL;

CREATE TABLE tags (
  name           TEXT PRIMARY KEY,        -- "static-analysis"
  description    TEXT NOT NULL,           -- required at first registration
  status         TEXT NOT NULL DEFAULT 'active', -- active | deprecated
  alias_to       TEXT REFERENCES tags(name),     -- nullable
  payload_schema JSON,                           -- nullable; optional JSON schema
                                                 -- for normalizing emits with this tag
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
- `alias_to` must point at an *active* tag at write time (`deprecate_tag` and `propose_alias` reject otherwise). This keeps alias resolution to a single hop in `find_capable`. If a chain becomes desirable later, lookup can grow to follow multiple hops without changing the on-disk shape

### Capability binding lifecycle
- Bindings track `(cell, tag, declared_at, last_refreshed_at)`
- `refresh_capabilities` extends `last_refreshed_at` on all of a cell's bindings to now
- `declare_capability` against an existing `(cell, tag)` is the same path: `last_refreshed_at` is bumped, `declared_at` is preserved
- Bindings with `last_refreshed_at < now - threshold_days` are stale; excluded from `find_capable`
- Stale bindings remain in the table for audit (no hard delete)
- `revoke_capability` is a hard delete — distinct from staleness. Stale = "haven't refreshed in a while"; revoke = "I retract this". The cell asserts a clear intent, so audit value is low and the binding goes. The tag itself survives (other cells may still declare it, and it stays addressable for `deprecate_tag`)
- `sweep_stale_capabilities` is observational — it returns the bindings older than the cutoff but does not mutate them (the binding schema has no stale-status column; staleness is read-time-only). `find_capable` filters stale bindings out at query time using the same threshold. The sweep is the operator-facing handle on that computation

### Cell lifecycle
- `active`: discoverable, capabilities matched
- `inactive`: not discoverable but record retained
- `register_cell` is idempotent on `name` — re-registering an existing name returns the existing `cell_id`. Prevents accidental duplicates from re-spawning agents.
- `induced_by` (when set) is unique across cells — second registration with the same `induced_by` fails with a clear error, resolving spawn-race conditions at register time.

### Tag schema lifecycle
- A tag's `payload_schema` is set/updated by operator via `set_tag_schema`. There's no schema-versioning story (yet); schema changes apply forward immediately.
- Cells fetching a stale schema isn't catastrophic — they emit slightly-old-shape payloads, which morphogen accepts; concentration may fragment briefly until cells refresh.
- For backward-incompatible changes, follow the tag-deprecation pattern: deprecate the old tag, register a new one, alias old → new.

## Open questions

1. **Similarity threshold for fragmentation suggestions** — needs tuning during early use. Start permissive (return suggestions on any non-trivial overlap), tighten if signal-to-noise is bad.
2. **Whether `find_capable` should ever expose `inactive` cells** — probably no, but a flag for archaeological queries (`include_inactive=true`) might be useful for operator tools.
3. **Cell-proposed aliases** — currently aliases are operator-managed only. Should cells be able to propose aliases for their own capabilities (`I declare 'sast' and 'static-analysis' are equivalent`)? Loosening this is a follow-up question — keep operator-only at first.
4. **Rate limiting on `declare_capability`** — probably not needed at colony scale, but worth noting. A cell that calls it 1000 times in a minute is buggy; reject above some sane threshold.
