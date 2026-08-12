-- ============================================================
-- 11_add_status_reason.sql
-- Adds the status_reason column to vlr_match_results, needed for the
-- mandatory reason a reviewer selects when manually linking two unmatched
-- entries together (Link Unmatched screen). See docs/Update Status.xlsx
-- for the fixed list of reasons; backend/src/domain/services/vlr/
-- status_reasons.py is the single source of truth used for validation.
--
-- Equivalent to alembic revision r5g6b7c8d9e0. Safe to run multiple times
-- (IF NOT EXISTS guard).
-- ============================================================

\connect vlr_db

ALTER TABLE public.vlr_match_results
    ADD COLUMN IF NOT EXISTS status_reason VARCHAR(100);

COMMENT ON COLUMN public.vlr_match_results.status_reason IS
    'Reviewer-selected reason for a manual link (see docs/Update Status.xlsx)';

-- Verify:
\echo 'status_reason column on vlr_match_results:'
SELECT column_name, data_type, character_maximum_length
FROM information_schema.columns
WHERE table_name = 'vlr_match_results' AND column_name = 'status_reason';
