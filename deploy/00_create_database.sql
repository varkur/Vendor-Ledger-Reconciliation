-- ============================================================
-- 00_create_database.sql
-- Creates the database, app user, and required extension.
-- Run as the postgres superuser:
--     sudo -u postgres psql -f 00_create_database.sql
--
-- Target DB/user match the app .env:
--     DATABASE_URL=postgresql+asyncpg://vlr_user:vlr_pass@localhost:5432/vlr_db
--
-- WARNING: the DROP DATABASE line deletes ALL existing data in
-- vlr_db. Comment it out if the DB already exists and you
-- only want to (re)create the user/extension.
-- ============================================================

-- Terminate active connections so DROP/CREATE can proceed
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'vlr_db' AND pid <> pg_backend_pid();

DROP DATABASE IF EXISTS vlr_db;

-- Create the application role if it doesn't already exist
DO
$$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'vlr_user') THEN
      CREATE ROLE vlr_user LOGIN PASSWORD 'vlr_pass';
   END IF;
END
$$;

CREATE DATABASE vlr_db OWNER vlr_user;

-- Grant schema ownership (PostgreSQL 15+) and enable the required extension.
\connect vlr_db
GRANT ALL ON SCHEMA public TO vlr_user;
ALTER SCHEMA public OWNER TO vlr_user;
CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;
