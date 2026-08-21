-- ============================================================
-- 17_soft_delete_request_1000-00017.sql
-- Reversibly "removes" reconciliation request 1000-00017 ("Testing
-- Submarine") so the vendor/period can be re-tried, WITHOUT physically
-- deleting any data.
--
-- IMPORTANT — this is NOT a true hide: vlr_reconciliation_requests has no
-- is_deleted column, and the Track Reconciliation list does not filter on
-- case deletion, so the request row will still appear in the list (with
-- status 'closed'). Soft-deleting the case(s) is what actually matters —
-- it's what the overlapping-period check queries, so it's what actually
-- unblocks creating a new request for the same vendor/period.
--
-- If you need the row to disappear from the list entirely, that requires
-- Option A (hard delete) instead — see 18_hard_delete_request.sql.
--
-- Safe to run multiple times (idempotent — only affects rows not already
-- soft-deleted / already closed).
-- ============================================================

\connect vlr_db

BEGIN;

-- 1. Soft-delete every case under this request — this is the check that
--    actually matters for retrying (has_overlapping_period joins on
--    ReconciliationCaseModel.is_deleted).
UPDATE public.vlr_reconciliation_cases
SET is_deleted = true,
    deleted_at = now()
WHERE request_id = (
    SELECT id FROM public.vlr_reconciliation_requests
    WHERE request_number = '1000-00017'
)
AND is_deleted = false;

-- 2. Mark the request itself as closed (cosmetic — the request row will
--    still show up in Track Reconciliation, just with status "Closed"
--    instead of "Open", since there's no is_deleted column on this table).
UPDATE public.vlr_reconciliation_requests
SET status = 'closed',
    modified_date = now(),
    modified_by = 'admin_manual_cleanup'
WHERE request_number = '1000-00017'
AND status <> 'closed';

COMMIT;

-- Verify:
\echo 'Case(s) soft-deleted for request 1000-00017:'
SELECT c.id, c.status, c.is_deleted, c.deleted_at
FROM public.vlr_reconciliation_cases c
JOIN public.vlr_reconciliation_requests r ON r.id = c.request_id
WHERE r.request_number = '1000-00017';

\echo 'Request status:'
SELECT id, request_number, title, status, period_start, period_end
FROM public.vlr_reconciliation_requests
WHERE request_number = '1000-00017';
