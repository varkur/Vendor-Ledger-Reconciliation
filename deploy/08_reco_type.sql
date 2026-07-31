-- ============================================================
-- 08_reco_type.sql
-- Adds reco_type ('bulk'/'direct') to vlr_reconciliation_requests and
-- backfills existing rows. Idempotent; safe to re-run.
--
--     sudo -u postgres psql -d vlr_db -v ON_ERROR_STOP=1 -f /tmp/08_reco_type.sql
--     sudo systemctl restart ledger-recon-backend.service
-- ============================================================

\connect vlr_db

ALTER TABLE public.vlr_reconciliation_requests
    ADD COLUMN IF NOT EXISTS reco_type VARCHAR(10) NOT NULL DEFAULT 'bulk';

CREATE INDEX IF NOT EXISTS ix_vlr_requests_reco_type
    ON public.vlr_reconciliation_requests (reco_type);

-- Backfill existing direct reconciliations (their cases are case_type='direct').
UPDATE public.vlr_reconciliation_requests r
SET reco_type = 'direct'
WHERE EXISTS (
    SELECT 1 FROM public.vlr_reconciliation_cases c
    WHERE c.request_id = r.id AND c.case_type = 'direct'
);

-- Keep alembic in sync with the new head.
UPDATE public.alembic_version SET version_num = 'q4f5a6b7c8d9';

ALTER TABLE public.vlr_reconciliation_requests OWNER TO vlr_user;
