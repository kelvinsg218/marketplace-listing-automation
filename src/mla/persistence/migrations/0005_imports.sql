-- 0005 import center: batches (history), planned rows (preview/report) and reusable mapping templates
CREATE TABLE import_batches (
    id            INTEGER PRIMARY KEY,
    source_name   TEXT    NOT NULL,
    source_path   TEXT    NOT NULL DEFAULT '',
    source_sha256 TEXT    NOT NULL DEFAULT '',
    format        TEXT    NOT NULL,
    target        TEXT    NOT NULL DEFAULT 'products' CHECK (target IN ('products', 'compatibility', 'images')),
    status        TEXT    NOT NULL DEFAULT 'planning'
                  CHECK (status IN ('planning', 'planned', 'committing', 'completed', 'cancelled', 'failed',
                                    'discarded')),
    mapping_json  TEXT    NOT NULL DEFAULT '{}',
    options_json  TEXT    NOT NULL DEFAULT '{}',
    counts_json   TEXT    NOT NULL DEFAULT '{}',
    message       TEXT    NOT NULL DEFAULT '',
    staging_dir   TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL,
    planned_at    TEXT,
    finished_at   TEXT
);
CREATE INDEX idx_import_batches_created ON import_batches(created_at);

CREATE TABLE import_rows (
    id           INTEGER PRIMARY KEY,
    batch_id     INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    row_no       INTEGER NOT NULL,
    action       TEXT    NOT NULL
                 CHECK (action IN ('create', 'update', 'unchanged', 'skip', 'error', 'review')),
    decision     TEXT    NOT NULL DEFAULT 'skip' CHECK (decision IN ('create', 'update', 'skip')),
    sku          TEXT    NOT NULL DEFAULT '',
    name         TEXT    NOT NULL DEFAULT '',
    product_id   INTEGER REFERENCES products(id) ON DELETE SET NULL,
    parent_sku   TEXT    NOT NULL DEFAULT '',
    data_json    TEXT    NOT NULL DEFAULT '{}',
    changes_json TEXT    NOT NULL DEFAULT '[]',
    issues_json  TEXT    NOT NULL DEFAULT '[]',
    media_json   TEXT    NOT NULL DEFAULT '[]',
    outcome      TEXT    NOT NULL DEFAULT '',
    UNIQUE (batch_id, row_no)
);
CREATE INDEX idx_import_rows_action ON import_rows(batch_id, action);

CREATE TABLE import_templates (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL COLLATE NOCASE UNIQUE,
    target       TEXT NOT NULL DEFAULT 'products',
    headers_json TEXT NOT NULL DEFAULT '[]',
    mapping_json TEXT NOT NULL DEFAULT '{}',
    options_json TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
