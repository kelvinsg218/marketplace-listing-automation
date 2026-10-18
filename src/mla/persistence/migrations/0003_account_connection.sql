-- 0003 seller URL, internal id, default flag and last connection check per account
ALTER TABLE marketplace_accounts ADD COLUMN seller_url TEXT NOT NULL DEFAULT '';
ALTER TABLE marketplace_accounts ADD COLUMN internal_id TEXT NOT NULL DEFAULT '';
ALTER TABLE marketplace_accounts ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1));
ALTER TABLE marketplace_accounts ADD COLUMN connection_status TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE marketplace_accounts ADD COLUMN connection_message TEXT NOT NULL DEFAULT '';
ALTER TABLE marketplace_accounts ADD COLUMN connection_checked_at TEXT;
ALTER TABLE marketplace_accounts ADD COLUMN detected_identity TEXT NOT NULL DEFAULT '';
ALTER TABLE marketplace_accounts ADD COLUMN last_connected_at TEXT;

UPDATE marketplace_accounts SET internal_id = marketplace || '-' || id WHERE internal_id = '';
UPDATE marketplace_accounts SET is_default = 1
 WHERE id IN (SELECT MIN(id) FROM marketplace_accounts GROUP BY marketplace);

CREATE UNIQUE INDEX idx_accounts_internal_id ON marketplace_accounts(internal_id COLLATE NOCASE)
 WHERE internal_id <> '';
