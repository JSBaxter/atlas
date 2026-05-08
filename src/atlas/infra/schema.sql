PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cells (
  id            TEXT PRIMARY KEY,
  name          TEXT UNIQUE NOT NULL,
  purpose       TEXT NOT NULL,
  repo_url      TEXT,
  registered_at TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'active',
  induced_by    TEXT
);

-- At most one cell per induced_by value (NULLs are unconstrained).
-- Mirrors SPEC's spawn-race protection at register time.
CREATE UNIQUE INDEX IF NOT EXISTS idx_cells_induced_by
  ON cells(induced_by) WHERE induced_by IS NOT NULL;

CREATE TABLE IF NOT EXISTS tags (
  name           TEXT PRIMARY KEY,
  description    TEXT NOT NULL,
  status         TEXT NOT NULL DEFAULT 'active',
  alias_to       TEXT REFERENCES tags(name),
  payload_schema TEXT,
  registered_at  TEXT NOT NULL,
  registered_by  TEXT NOT NULL REFERENCES cells(id)
);

CREATE TABLE IF NOT EXISTS capability_bindings (
  cell_id            TEXT NOT NULL REFERENCES cells(id),
  tag                TEXT NOT NULL REFERENCES tags(name),
  declared_at        TEXT NOT NULL,
  last_refreshed_at  TEXT NOT NULL,
  PRIMARY KEY (cell_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_bindings_tag       ON capability_bindings(tag);
CREATE INDEX IF NOT EXISTS idx_bindings_refreshed ON capability_bindings(last_refreshed_at);
CREATE INDEX IF NOT EXISTS idx_tags_status        ON tags(status);
