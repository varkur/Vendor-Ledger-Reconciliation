-- ============================================================
-- 04_incremental_changes.sql
-- Applies schema changes to an EXISTING vlr_db WITHOUT recreating it.
-- Safe to re-run (idempotent).
--
--     sudo -u postgres psql -d vlr_db -v ON_ERROR_STOP=1 -f /tmp/04_incremental_changes.sql
--
-- After running, restart the backend:
--     sudo systemctl restart ledger-recon-backend.service
-- ============================================================

\connect vlr_db

-- ------------------------------------------------------------
-- 1. Vendor sign-off: confirmation_text column
--    (portal sign-off endpoints write this; missing col caused 500s)
-- ------------------------------------------------------------
ALTER TABLE public.vlr_portal_sign_offs
    ADD COLUMN IF NOT EXISTS confirmation_text TEXT;

-- ------------------------------------------------------------
-- 2. Ledger export: raw_data JSON column
--    (stores full original uploaded row for the formatted Excel export)
-- ------------------------------------------------------------
ALTER TABLE public.vlr_ledger_entries
    ADD COLUMN IF NOT EXISTS raw_data JSON;

-- ------------------------------------------------------------
-- 3. Relax case status CHECK constraint to include workflow statuses
--    (mapping_pending, statement_mapped, in_progress, etc.)
--    Old constraint rejected newer statuses -> 500 on reupload /
--    start-reconciliation / review.
-- ------------------------------------------------------------
ALTER TABLE public.vlr_reconciliation_cases
    DROP CONSTRAINT IF EXISTS ck_vlr_case_valid_status;

ALTER TABLE public.vlr_reconciliation_cases
    ADD CONSTRAINT ck_vlr_case_valid_status CHECK (
        status IN (
            'created','ledger_confirmed','invited','data_received','matching','matched',
            'review','pending_approval','approved','signed_off','closed',
            'mapping_pending','statement_mapped','in_progress','auto_completed',
            'review_pending','reviewed','signoff_requested','signoff_completed','reco_rejected'
        )
    );

-- ------------------------------------------------------------
-- 4. Keep alembic in sync so `alembic upgrade head` is a no-op
--    (matches the head migration n1c2d3e4f5a6)
-- ------------------------------------------------------------
UPDATE public.alembic_version SET version_num = 'n1c2d3e4f5a6';

-- Ensure the app user still owns the altered objects (harmless if already owner)
ALTER TABLE public.vlr_portal_sign_offs      OWNER TO vlr_user;
ALTER TABLE public.vlr_ledger_entries        OWNER TO vlr_user;
ALTER TABLE public.vlr_reconciliation_cases  OWNER TO vlr_user;
