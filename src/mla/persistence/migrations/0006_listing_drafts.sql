-- 0006 listings become prepared offers: per-account content overrides and the full lifecycle
-- (draft → incomplete → ready for review → approved → queued → running → published / failed / needs attention).
-- SQLite cannot widen a CHECK constraint, so the table is rebuilt and every row copied.
CREATE TABLE listings_new (
    id              INTEGER PRIMARY KEY,
    product_id      INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    marketplace     TEXT    NOT NULL,
    account_id      INTEGER NOT NULL REFERENCES marketplace_accounts(id),
    status          TEXT    NOT NULL
                    CHECK (status IN ('draft', 'incomplete', 'ready', 'approved', 'queued', 'running',
                                      'awaiting_review', 'published', 'failed', 'needs_attention', 'cancelled')),
    external_id     TEXT    NOT NULL DEFAULT '',
    url             TEXT    NOT NULL DEFAULT '',
    published_at    TEXT,
    last_item_id    INTEGER REFERENCES automation_job_items(id) ON DELETE SET NULL,
    updated_at      TEXT    NOT NULL,
    -- overrides: empty / NULL means "use the master product"
    title           TEXT    NOT NULL DEFAULT '',
    description     TEXT    NOT NULL DEFAULT '',
    price_cents     INTEGER CHECK (price_cents IS NULL OR price_cents >= 0),
    stock           INTEGER CHECK (stock IS NULL OR stock >= 0),
    category_id     TEXT    NOT NULL DEFAULT '',
    listing_type    TEXT    NOT NULL DEFAULT '',
    attributes_json TEXT    NOT NULL DEFAULT '{}',
    images_json     TEXT    NOT NULL DEFAULT '[]',
    notes           TEXT    NOT NULL DEFAULT '',
    approved_at     TEXT,
    approved_hash   TEXT    NOT NULL DEFAULT '',  -- fingerprint of the content the user approved
    created_at      TEXT    NOT NULL,
    UNIQUE (product_id, marketplace, account_id)
);
INSERT INTO listings_new (id, product_id, marketplace, account_id, status, external_id, url, published_at,
                          last_item_id, updated_at, created_at)
SELECT id, product_id, marketplace, account_id, status, external_id, url, published_at, last_item_id, updated_at,
       updated_at
  FROM listings;
DROP TABLE listings;
ALTER TABLE listings_new RENAME TO listings;
CREATE INDEX idx_listings_status ON listings(status);
CREATE INDEX idx_listings_account ON listings(marketplace, account_id, status);

-- items that ended in "check manually" were stored as plain failures before this version
UPDATE listings SET status = 'needs_attention'
 WHERE status = 'failed'
   AND last_item_id IN (SELECT id FROM automation_job_items WHERE status = 'needs_attention');
