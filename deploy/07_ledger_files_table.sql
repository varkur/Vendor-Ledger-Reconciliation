-- ============================================================
-- 07_ledger_files_table.sql
-- Creates vlr_ledger_files to store the ORIGINAL uploaded ledger bytes
-- (per case + side) so downloads return the exact original file.
-- Idempotent; safe to re-run.
--
--     sudo -u postgres psql -d vlr_db -v ON_ERROR_STOP=1 -f /tmp/07_ledger_files_table.sql
--     sudo systemctl restart ledger-recon-backend.service
-- ============================================================

\connect vlr_db

CREATE TABLE IF NOT EXISTS public.vlr_ledger_files (
    id            UUID PRIMARY KEY,
    case_id       UUID NOT NULL REFERENCES public.vlr_reconciliation_cases(id) ON DELETE CASCADE,
    side          VARCHAR(10) NOT NULL,
    filename      VARCHAR(255) NOT NULL,
    content_type  VARCHAR(150) NOT NULL DEFAULT 'application/octet-stream',
    content       BYTEA NOT NULL,
    created_by    VARCHAR(255) NOT NULL DEFAULT 'system',
    created_date  TIMESTAMPTZ NOT NULL DEFAULT now(),
    modified_by   VARCHAR(255) NOT NULL DEFAULT 'system',
    modified_date TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_vlr_ledger_file_case_side UNIQUE (case_id, side)
);

CREATE INDEX IF NOT EXISTS ix_vlr_ledger_files_case_id
    ON public.vlr_ledger_files (case_id);

-- Keep alembic in sync with the new head.
UPDATE public.alembic_version SET version_num = 'p3e4f5a6b7c8';

ALTER TABLE public.vlr_ledger_files OWNER TO vlr_user;
