# Changelog

All notable changes to this cell are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this cell adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Initial cell scaffold from
  [`stem-cell`](https://github.com/JSBaxter/stem-cell).
- Cell-root Python project (`pyproject.toml`, `src/atlas/`,
  `tests/`) with `uv`, `ruff`, `ty`, and `pytest` wired up via
  pre-commit hooks. Smoke tests pass; no feature code yet. CI mirror
  pending (bot lacks `workflows` permission to push workflow
  changes — see STATE.md).
- Domain layer foundation: `Cell`, `Tag`, `CapabilityBinding`
  models, `AtlasRepository` Protocol, `Registry` service.
  Cell-lifecycle operations: `register_cell` (idempotent on name,
  spawn-race-safe via unique `induced_by`), `set_cell_status`,
  `get_cell`, `list_cells`. In-memory test fixture only.
- Capability declarations: `declare_capability` (auto-registers
  tag on first declare; description required at first
  registration; re-declare bumps `last_refreshed_at`),
  `revoke_capability` (hard delete; tag survives),
  `refresh_capabilities` (heartbeat), `list_capabilities`.
  Suggestion field returns `[]` until the similarity algorithm
  lands. SPEC.md updated to record `revoke = hard delete`,
  distinct from staleness.
- Tag admin: `deprecate_tag` (with optional `alias_to`),
  `propose_alias` (operator-managed redirect; canonical must be
  active), `set_tag_schema` (opaque JSON payload schema),
  `list_tags` (returns `TagListing` with per-tag `usage_count`),
  `get_tag_schema`. SPEC.md updated to record that `alias_to` must
  point at an active tag at write time, keeping resolution to a
  single hop.
- Discovery: `find_capable` (implicit dot-hierarchy prefix
  matching in both directions, transparent alias resolution
  forward AND reverse, stale-binding exclusion at the 14-day
  threshold, inactive-cell exclusion; modes `all` / `any`),
  `find_induced_by`, `sweep_stale_capabilities`
  (observational — returns `StaleBindingsReport`, no mutation).
  SPEC.md updated to record alias-resolution-is-bidirectional
  and sweep-is-observational. The in-memory domain layer is now
  feature-complete; PR 3 swaps in SQLite without touching domain
  code.

### Changed

- (nothing)

### Deprecated

- (nothing)

### Removed

- (nothing)

### Fixed

- (nothing)

### Security

- (nothing)

[Unreleased]: about:blank
