-- ============================================================
-- 05_request_columns.sql
-- Adds request_number, title, sent_date to vlr_reconciliation_requests.
-- Idempotent; safe to re-run.
--
--     sudo -u postgres psql -d vlr_db -v ON_ERROR_STOP=1 -f /tmp/05_request_columns.sql
--     sudo systemctl restart ledger-recon-backend.service
-- ============================================================

\connect vlr_db

ALTER TABLE public.vlr_reconciliation_requests
    ADD COLUMN IF NOT EXISTS request_number VARCHAR(30);

ALTER TABLE public.vlr_reconciliation_requests
    ADD COLUMN IF NOT EXISTS title VARCHAR(255);

ALTER TABLE public.vlr_reconciliation_requests
    ADD COLUMN IF NOT EXISTS sent_date TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_vlr_requests_request_number
    ON public.vlr_reconciliation_requests (request_number);

-- Keep alembic in sync with the new head.
UPDATE public.alembic_version SET version_num = 'o2d3e4f5a6b7';

ALTER TABLE public.vlr_reconciliation_requests OWNER TO vlr_user;
