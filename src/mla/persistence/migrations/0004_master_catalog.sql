-- 0004 master catalog: identification, commercial and technical fields, media links, compatibility.
-- Additive only: every new column is optional and existing rows keep their data.
ALTER TABLE products ADD COLUMN commercial_name TEXT NOT NULL DEFAULT '';
ALTER TABLE products ADD COLUMN manufacturer_code TEXT NOT NULL DEFAULT '';
ALTER TABLE products ADD COLUMN gtin TEXT NOT NULL DEFAULT '';
ALTER TABLE products ADD COLUMN supplier TEXT NOT NULL DEFAULT '';
ALTER TABLE products ADD COLUMN cost_cents INTEGER CHECK (cost_cents IS NULL OR cost_cents >= 0);
ALTER TABLE products ADD COLUMN promo_price_cents INTEGER CHECK (promo_price_cents IS NULL OR promo_price_cents >= 0);
ALTER TABLE products ADD COLUMN min_stock INTEGER CHECK (min_stock IS NULL OR min_stock >= 0);
ALTER TABLE products ADD COLUMN unit TEXT NOT NULL DEFAULT '';
ALTER TABLE products ADD COLUMN commercial_status TEXT NOT NULL DEFAULT 'active'
    CHECK (commercial_status IN ('active', 'inactive', 'discontinued'));
ALTER TABLE products ADD COLUMN original_description TEXT NOT NULL DEFAULT '';
ALTER TABLE products ADD COLUMN technical_description TEXT NOT NULL DEFAULT '';
ALTER TABLE products ADD COLUMN color TEXT NOT NULL DEFAULT '';
ALTER TABLE products ADD COLUMN specs_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE products ADD COLUMN custom_attributes_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE products ADD COLUMN manufacturer_refs TEXT NOT NULL DEFAULT '';
ALTER TABLE products ADD COLUMN internal_notes TEXT NOT NULL DEFAULT '';
ALTER TABLE products ADD COLUMN source TEXT NOT NULL DEFAULT '';

CREATE INDEX idx_products_gtin ON products(gtin) WHERE gtin <> '';
CREATE INDEX idx_products_mfr_code ON products(manufacturer_code COLLATE NOCASE) WHERE manufacturer_code <> '';
CREATE INDEX idx_products_brand ON products(brand COLLATE NOCASE);
CREATE INDEX idx_products_category ON products(category COLLATE NOCASE);
CREATE INDEX idx_products_supplier ON products(supplier COLLATE NOCASE) WHERE supplier <> '';
CREATE INDEX idx_products_name ON products(internal_name COLLATE NOCASE);

-- images: optional link to one variation (by variation name) and the file name it was imported from
ALTER TABLE product_images ADD COLUMN variant TEXT NOT NULL DEFAULT '';
ALTER TABLE product_images ADD COLUMN original_name TEXT NOT NULL DEFAULT '';
CREATE INDEX idx_images_sha ON product_images(sha256);

-- technical files (manuals, datasheets) stored content-addressed under files/
CREATE TABLE product_files (
    id            INTEGER PRIMARY KEY,
    product_id    INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    filename      TEXT    NOT NULL,
    original_name TEXT    NOT NULL DEFAULT '',
    size_bytes    INTEGER NOT NULL DEFAULT 0,
    sha256        TEXT    NOT NULL DEFAULT '',
    position      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL
);
CREATE INDEX idx_files_product ON product_files(product_id, position);

-- media that a source referenced but MLA could not find (resolved later by name)
CREATE TABLE product_missing_media (
    id         INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    reference  TEXT    NOT NULL,
    kind       TEXT    NOT NULL DEFAULT 'image' CHECK (kind IN ('image', 'file')),
    origin     TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL,
    UNIQUE (product_id, reference, kind)
);

CREATE TABLE product_compatibilities (
    id             INTEGER PRIMARY KEY,
    product_id     INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    brand          TEXT    NOT NULL DEFAULT '',
    model          TEXT    NOT NULL,
    version        TEXT    NOT NULL DEFAULT '',
    year_from      INTEGER CHECK (year_from IS NULL OR year_from BETWEEN 1900 AND 2100),
    year_to        INTEGER CHECK (year_to IS NULL OR year_to BETWEEN 1900 AND 2100),
    reference_code TEXT    NOT NULL DEFAULT '',
    notes          TEXT    NOT NULL DEFAULT '',
    source         TEXT    NOT NULL DEFAULT 'client'
                   CHECK (source IN ('client', 'manufacturer', 'external', 'ai')),
    source_detail  TEXT    NOT NULL DEFAULT '',
    verification   TEXT    NOT NULL DEFAULT 'unverified'
                   CHECK (verification IN ('confirmed', 'unverified', 'rejected')),
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL,
    CHECK (year_from IS NULL OR year_to IS NULL OR year_from <= year_to)
);
CREATE INDEX idx_compat_product ON product_compatibilities(product_id);
CREATE INDEX idx_compat_target ON product_compatibilities(brand COLLATE NOCASE, model COLLATE NOCASE);
CREATE UNIQUE INDEX idx_compat_unique ON product_compatibilities(
    product_id, brand COLLATE NOCASE, model COLLATE NOCASE, version COLLATE NOCASE,
    IFNULL(year_from, 0), IFNULL(year_to, 0));
