-- Runs once when the development PostgreSQL volume is created.
-- The application role is NOT a superuser: PostgreSQL superusers bypass row-level security.
CREATE ROLE mla LOGIN PASSWORD 'mla-dev-password' NOSUPERUSER NOCREATEROLE;
CREATE DATABASE mla OWNER mla;
CREATE DATABASE mla_test OWNER mla;
