-- 0007 groundwork for market intelligence and optimisation suggestions.
-- Three kinds of information stay in separate tables: client data (catalog), external observations
-- (market_*, always with source and collection date) and AI suggestions (never applied without the user).
CREATE TABLE market_references (
    id          INTEGER PRIMARY KEY,
    product_id  INTEGER REFERENCES products(id) ON DELETE CASCADE,
    marketplace TEXT    NOT NULL DEFAULT '',
    url         TEXT    NOT NULL,
    title       TEXT    NOT NULL DEFAULT '',
    notes       TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL,
    UNIQUE (product_id, url)
);

CREATE TABLE market_observations (
    id           INTEGER PRIMARY KEY,
    reference_id INTEGER NOT NULL REFERENCES market_references(id) ON DELETE CASCADE,
    kind         TEXT    NOT NULL CHECK (kind IN ('price', 'title', 'description', 'question', 'review', 'rating',
                                                  'other')),
    value_text   TEXT    NOT NULL DEFAULT '',
    value_cents  INTEGER,
    source       TEXT    NOT NULL CHECK (source IN ('manual', 'official_api', 'collector')),
    collector    TEXT    NOT NULL DEFAULT '',
    collected_at TEXT    NOT NULL,
    notes        TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX idx_observations_reference ON market_observations(reference_id, kind, collected_at);

CREATE TABLE ai_suggestions (
    id             INTEGER PRIMARY KEY,
    listing_id     INTEGER REFERENCES listings(id) ON DELETE CASCADE,
    product_id     INTEGER REFERENCES products(id) ON DELETE CASCADE,
    field          TEXT    NOT NULL,
    current_value  TEXT    NOT NULL DEFAULT '',
    proposed_value TEXT    NOT NULL,
    rationale      TEXT    NOT NULL DEFAULT '',
    provider       TEXT    NOT NULL,
    model          TEXT    NOT NULL DEFAULT '',
    status         TEXT    NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected')),
    created_at     TEXT    NOT NULL,
    decided_at     TEXT
);
CREATE INDEX idx_suggestions_listing ON ai_suggestions(listing_id, status);
