-- 0008 field-level history of the master catalog: who/what changed each field and when.
-- Rows survive the product's deletion (product_id becomes NULL; the SKU stays for traceability).
CREATE TABLE product_changes (
    id          INTEGER PRIMARY KEY,
    product_id  INTEGER REFERENCES products(id) ON DELETE SET NULL,
    sku         TEXT    NOT NULL DEFAULT '',
    field       TEXT    NOT NULL,
    label       TEXT    NOT NULL,
    old_value   TEXT    NOT NULL DEFAULT '',
    new_value   TEXT    NOT NULL DEFAULT '',
    source      TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);
CREATE INDEX idx_product_changes_product ON product_changes(product_id, id);
CREATE INDEX idx_product_changes_created ON product_changes(created_at);
