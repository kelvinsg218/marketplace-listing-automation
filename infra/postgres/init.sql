-- Development/test setup. Run with psql as a superuser:
--   psql -U postgres -h localhost -f infra/postgres/init.sql
-- Idempotent and non-destructive: it only creates what is missing and never changes an existing role (including its
-- password) or database. The application role is NOT a superuser: PostgreSQL superusers bypass row-level security.
SELECT 'CREATE ROLE mla LOGIN PASSWORD ''mla-dev-password'' NOSUPERUSER NOCREATEROLE'
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mla')\gexec
SELECT 'CREATE DATABASE mla OWNER mla'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'mla')\gexec
SELECT 'CREATE DATABASE mla_test OWNER mla'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'mla_test')\gexec
-- Report what exists now (nothing above alters an existing object).
SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'mla';
SELECT datname, pg_get_userbyid(datdba) AS owner FROM pg_database WHERE datname IN ('mla', 'mla_test');
