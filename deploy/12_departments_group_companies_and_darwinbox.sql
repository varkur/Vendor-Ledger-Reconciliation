-- ============================================================
-- 12_departments_group_companies_and_darwinbox.sql
-- Applies schema changes for the user-provisioning feature to an EXISTING
-- vlr_db WITHOUT recreating it. Idempotent; safe to re-run.
--
-- Adds:
--   1. departments            (lookup table, case-insensitive unique name)
--   2. group_companies        (lookup table, case-insensitive unique name)
--   3. user_details.department_id / group_company_id (nullable FKs)
--
-- Equivalent to Alembic revision t7i8j9k0l1m2.
--
--     sudo -u postgres psql -d vlr_db -v ON_ERROR_STOP=1 -f /tmp/12_departments_group_companies_and_darwinbox.sql
--
-- After running, restart the backend:
--     sudo systemctl restart ledger-recon-backend.service
-- ============================================================

\connect vlr_db

-- ------------------------------------------------------------
-- 1. departments lookup table
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.departments (
    id            UUID PRIMARY KEY,
    name          VARCHAR(255) NOT NULL,
    is_active     BOOLEAN NOT NULL,
    created_by    VARCHAR(255) NOT NULL,
    created_date  TIMESTAMPTZ NOT NULL,
    modified_by   VARCHAR(255) NOT NULL,
    modified_date TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_departments_name
    ON public.departments (name);

CREATE UNIQUE INDEX IF NOT EXISTS ix_departments_name_lower_unique
    ON public.departments (lower(name));

-- ------------------------------------------------------------
-- 2. group_companies lookup table
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.group_companies (
    id            UUID PRIMARY KEY,
    name          VARCHAR(255) NOT NULL,
    is_active     BOOLEAN NOT NULL,
    created_by    VARCHAR(255) NOT NULL,
    created_date  TIMESTAMPTZ NOT NULL,
    modified_by   VARCHAR(255) NOT NULL,
    modified_date TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_group_companies_name
    ON public.group_companies (name);

CREATE UNIQUE INDEX IF NOT EXISTS ix_group_companies_name_lower_unique
    ON public.group_companies (lower(name));

-- ------------------------------------------------------------
-- 3. user_details FK columns (nullable, ON DELETE SET NULL)
--    Existing free-text department/group_company columns are untouched.
-- ------------------------------------------------------------
ALTER TABLE public.user_details
    ADD COLUMN IF NOT EXISTS department_id UUID;

ALTER TABLE public.user_details
    ADD COLUMN IF NOT EXISTS group_company_id UUID;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_user_details_department_id'
    ) THEN
        ALTER TABLE public.user_details
            ADD CONSTRAINT fk_user_details_department_id
            FOREIGN KEY (department_id) REFERENCES public.departments(id)
            ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_user_details_group_company_id'
    ) THEN
        ALTER TABLE public.user_details
            ADD CONSTRAINT fk_user_details_group_company_id
            FOREIGN KEY (group_company_id) REFERENCES public.group_companies(id)
            ON DELETE SET NULL;
    END IF;
END $$;

-- ------------------------------------------------------------
-- 4. Keep alembic in sync so `alembic upgrade head` is a no-op
--    (matches the head migration t7i8j9k0l1m2)
-- ------------------------------------------------------------
UPDATE public.alembic_version SET version_num = 't7i8j9k0l1m2';

-- Ensure the app user owns the new/altered objects.
ALTER TABLE public.departments      OWNER TO vlr_user;
ALTER TABLE public.group_companies  OWNER TO vlr_user;
ALTER TABLE public.user_details     OWNER TO vlr_user;

-- Verify:
\echo 'departments / group_companies tables + user_details FK columns:'
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_name IN ('departments', 'group_companies')
   OR (table_name = 'user_details' AND column_name IN ('department_id', 'group_company_id'))
ORDER BY table_name, column_name;
