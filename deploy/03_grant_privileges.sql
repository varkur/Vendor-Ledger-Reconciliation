-- ============================================================
-- 03_grant_privileges.sql
-- Run AFTER 01_schema.sql and 02_seed_data.sql.
-- Because the schema/seed were loaded as the postgres superuser,
-- all tables/sequences are owned by postgres. The app connects as
-- vlr_user, so grant it full access and make it own every object.
--
--     sudo -u postgres psql -d vlr_db -v ON_ERROR_STOP=1 -f 03_grant_privileges.sql
-- ============================================================

\connect vlr_db

-- Grant privileges on all existing objects
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO vlr_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO vlr_user;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO vlr_user;

-- Default privileges for any objects created later
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO vlr_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO vlr_user;

-- Reassign ownership of every table, sequence and view to vlr_user
DO
$$
DECLARE
   r RECORD;
BEGIN
   FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public'
   LOOP
      EXECUTE format('ALTER TABLE public.%I OWNER TO vlr_user;', r.tablename);
   END LOOP;

   FOR r IN SELECT sequencename FROM pg_sequences WHERE schemaname = 'public'
   LOOP
      EXECUTE format('ALTER SEQUENCE public.%I OWNER TO vlr_user;', r.sequencename);
   END LOOP;

   FOR r IN SELECT viewname FROM pg_views WHERE schemaname = 'public'
   LOOP
      EXECUTE format('ALTER VIEW public.%I OWNER TO vlr_user;', r.viewname);
   END LOOP;
END
$$;
