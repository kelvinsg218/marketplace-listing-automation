-- 0001 initial schema
CREATE TABLE products (
    id                INTEGER PRIMARY KEY,
    internal_name     TEXT    NOT NULL,
    title             TEXT    NOT NULL DEFAULT '',
    sku               TEXT    NOT NULL COLLATE NOCASE UNIQUE,
    category          TEXT    NOT NULL DEFAULT '',
    subcategory       TEXT    NOT NULL DEFAULT '',
    brand             TEXT    NOT NULL DEFAULT '',
    model             TEXT    NOT NULL DEFAULT '',
    condition         TEXT    NOT NULL DEFAULT 'new' CHECK (condition IN ('new', 'used', 'refurbished')),
    description       TEXT    NOT NULL DEFAULT '',
    features          TEXT    NOT NULL DEFAULT '',
    material          TEXT    NOT NULL DEFAULT '',
    package_contents  TEXT    NOT NULL DEFAULT '',
    warranty          TEXT    NOT NULL DEFAULT '',
    price_cents       INTEGER CHECK (price_cents IS NULL OR price_cents >= 0),
    stock             INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    weight_g          INTEGER CHECK (weight_g IS NULL OR weight_g >= 0),
    length_mm         INTEGER CHECK (length_mm IS NULL OR length_mm >= 0),
    width_mm          INTEGER CHECK (width_mm IS NULL OR width_mm >= 0),
    height_mm         INTEGER CHECK (height_mm IS NULL OR height_mm >= 0),
    package_type      TEXT    NOT NULL DEFAULT '',
    availability_days INTEGER CHECK (availability_days IS NULL OR availability_days >= 0),
    shipping_notes    TEXT    NOT NULL DEFAULT '',
    status            TEXT    NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'incomplete', 'ready')),
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL
);
CREATE INDEX idx_products_status ON products(status);
CREATE INDEX idx_products_updated ON products(updated_at);

CREATE TABLE product_images (
    id          INTEGER PRIMARY KEY,
    product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    filename    TEXT    NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0,
    is_main     INTEGER NOT NULL DEFAULT 0 CHECK (is_main IN (0, 1)),
    width       INTEGER NOT NULL DEFAULT 0,
    height      INTEGER NOT NULL DEFAULT 0,
    size_bytes  INTEGER NOT NULL DEFAULT 0,
    sha256      TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL
);
CREATE INDEX idx_images_product ON product_images(product_id, position);

CREATE TABLE product_variants (
    id              INTEGER PRIMARY KEY,
    product_id      INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    name            TEXT    NOT NULL,
    attributes_json TEXT    NOT NULL DEFAULT '{}',
    sku             TEXT    COLLATE NOCASE UNIQUE,
    price_cents     INTEGER CHECK (price_cents IS NULL OR price_cents >= 0),
    stock           INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
    position        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_variants_product ON product_variants(product_id, position);

CREATE TABLE product_marketplace_data (
    id              INTEGER PRIMARY KEY,
    product_id      INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    marketplace     TEXT    NOT NULL,
    enabled         INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    price_cents     INTEGER CHECK (price_cents IS NULL OR price_cents >= 0),
    category_id     TEXT    NOT NULL DEFAULT '',
    listing_type    TEXT    NOT NULL DEFAULT '',
    attributes_json TEXT    NOT NULL DEFAULT '{}',
    UNIQUE (product_id, marketplace)
);

CREATE TABLE product_groups (
    id                INTEGER PRIMARY KEY,
    name              TEXT NOT NULL COLLATE NOCASE UNIQUE,
    description       TEXT NOT NULL DEFAULT '',
    marketplaces_json TEXT NOT NULL DEFAULT '[]',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE TABLE group_products (
    group_id   INTEGER NOT NULL REFERENCES product_groups(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    position   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (group_id, product_id)
);
CREATE INDEX idx_group_products_product ON group_products(product_id);

CREATE TABLE marketplace_accounts (
    id          INTEGER PRIMARY KEY,
    marketplace TEXT    NOT NULL,
    label       TEXT    NOT NULL,
    profile_dir TEXT    NOT NULL DEFAULT '',
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at  TEXT    NOT NULL,
    UNIQUE (marketplace, label)
);

CREATE TABLE automation_jobs (
    id          INTEGER PRIMARY KEY,
    label       TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'product' CHECK (kind IN ('product', 'group', 'batch')),
    group_id    INTEGER REFERENCES product_groups(id) ON DELETE SET NULL,
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'paused', 'completed', 'cancelled')),
    created_at  TEXT NOT NULL,
    started_at  TEXT,
    finished_at TEXT
);
CREATE INDEX idx_jobs_status ON automation_jobs(status);

CREATE TABLE automation_job_items (
    id          INTEGER PRIMARY KEY,
    job_id      INTEGER NOT NULL REFERENCES automation_jobs(id) ON DELETE CASCADE,
    -- history survives product deletion: keep a snapshot of name/SKU
    product_id  INTEGER REFERENCES products(id) ON DELETE SET NULL,
    product_name TEXT   NOT NULL DEFAULT '',
    sku         TEXT    NOT NULL DEFAULT '',
    marketplace TEXT    NOT NULL,
    account_id  INTEGER NOT NULL REFERENCES marketplace_accounts(id),
    position    INTEGER NOT NULL DEFAULT 0,
    status      TEXT    NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'awaiting_review', 'published', 'failed',
                                  'cancelled', 'skipped', 'needs_attention')),
    step        TEXT    NOT NULL DEFAULT '',
    attempts    INTEGER NOT NULL DEFAULT 0,
    error       TEXT    NOT NULL DEFAULT '',
    external_id TEXT    NOT NULL DEFAULT '',
    url         TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL,
    started_at  TEXT,
    finished_at TEXT
);
CREATE INDEX idx_items_job ON automation_job_items(job_id, position);
CREATE INDEX idx_items_status ON automation_job_items(status);
CREATE INDEX idx_items_target ON automation_job_items(product_id, marketplace, account_id);

CREATE TABLE listings (
    id           INTEGER PRIMARY KEY,
    product_id   INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    marketplace  TEXT    NOT NULL,
    account_id   INTEGER NOT NULL REFERENCES marketplace_accounts(id),
    status       TEXT    NOT NULL
                 CHECK (status IN ('draft', 'incomplete', 'ready', 'queued', 'running', 'awaiting_review',
                                   'published', 'failed', 'cancelled')),
    external_id  TEXT    NOT NULL DEFAULT '',
    url          TEXT    NOT NULL DEFAULT '',
    published_at TEXT,
    last_item_id INTEGER REFERENCES automation_job_items(id) ON DELETE SET NULL,
    updated_at   TEXT    NOT NULL,
    UNIQUE (product_id, marketplace, account_id)
);
CREATE INDEX idx_listings_status ON listings(status);

CREATE TABLE execution_logs (
    id           INTEGER PRIMARY KEY,
    job_id       INTEGER REFERENCES automation_jobs(id) ON DELETE CASCADE,
    item_id      INTEGER REFERENCES automation_job_items(id) ON DELETE CASCADE,
    product_id   INTEGER REFERENCES products(id) ON DELETE SET NULL,
    marketplace  TEXT NOT NULL DEFAULT '',
    level        TEXT NOT NULL,
    step         TEXT NOT NULL DEFAULT '',
    message      TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    screenshot   TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL
);
CREATE INDEX idx_logs_item ON execution_logs(item_id);
CREATE INDEX idx_logs_created ON execution_logs(created_at);

CREATE TABLE application_settings (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE license_state (
    id               INTEGER PRIMARY KEY CHECK (id = 1),
    installation_id  TEXT NOT NULL,
    license_key      TEXT NOT NULL DEFAULT '',
    plan             TEXT NOT NULL DEFAULT 'trial',
    status           TEXT NOT NULL DEFAULT 'trial',
    trial_started_at TEXT NOT NULL,
    activated_at     TEXT,
    expires_at       TEXT,
    updated_at       TEXT NOT NULL
);
