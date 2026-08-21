-- ============================================================
-- 15_add_ledger_upload_staging.sql
-- Adds the vlr_ledger_upload_staging table — a staging area for a
-- consolidated (multi-vendor, PAN-per-row) company ledger uploaded BEFORE
-- any request/cases exist. The upload is parsed and matched against the
-- vendor master first; only once confirmed does the app create the
-- ReconciliationRequest + one case per matched vendor.
--
-- Equivalent to alembic revision s6h7c8d9e0f1. Safe to run multiple times
-- (IF NOT EXISTS guards).
-- ============================================================

\connect vlr_db

CREATE TABLE IF NOT EXISTS public.vlr_ledger_upload_staging (
    id UUID PRIMARY KEY,
    company_code VARCHAR(20) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    content_type VARCHAR(150) NOT NULL DEFAULT 'application/octet-stream',
    content BYTEA NOT NULL,
    request_params JSON NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_by VARCHAR(255) NOT NULL DEFAULT 'system',
    created_date TIMESTAMPTZ NOT NULL DEFAULT now(),
    modified_by VARCHAR(255) NOT NULL DEFAULT 'system',
    modified_date TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_vlr_ledger_upload_staging_company_code
    ON public.vlr_ledger_upload_staging (company_code);

-- Verify:
\echo 'vlr_ledger_upload_staging table:'
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'vlr_ledger_upload_staging'
ORDER BY ordinal_position;
