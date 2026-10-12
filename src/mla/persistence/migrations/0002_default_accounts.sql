-- 0002 one default account per marketplace so the first run works without setup
INSERT OR IGNORE INTO marketplace_accounts (marketplace, label, created_at)
VALUES ('mercadolivre', 'Conta principal', strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
       ('shopee',       'Conta principal', strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
       ('simulado',     'Conta de teste',  strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'));
