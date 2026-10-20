-- 0009 official marketplace API connection per account (OAuth). Secrets are DPAPI-encrypted blobs bound to the
-- Windows user; never plain text. Deleting the account removes its credentials.
CREATE TABLE marketplace_api_credentials (
    account_id        INTEGER PRIMARY KEY REFERENCES marketplace_accounts(id) ON DELETE CASCADE,
    provider          TEXT    NOT NULL,
    client_id         TEXT    NOT NULL,
    client_secret_enc BLOB    NOT NULL,
    redirect_uri      TEXT    NOT NULL,
    access_token_enc  BLOB,
    refresh_token_enc BLOB,
    expires_at        TEXT,
    remote_user_id    TEXT    NOT NULL DEFAULT '',
    nickname          TEXT    NOT NULL DEFAULT '',
    connected_at      TEXT,
    checked_at        TEXT,
    last_error        TEXT    NOT NULL DEFAULT '',
    updated_at        TEXT    NOT NULL
);
