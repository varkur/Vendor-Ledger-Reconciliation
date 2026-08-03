-- ============================================================
-- 09_fix_period_dates.sql
-- Corrects reconciliation period dates that were stored one day earlier.
--
-- CAUSE: the frontend used Date.toISOString() to build the YYYY-MM-DD value.
-- That converts the local date to UTC first, so a date picked in IST (+5:30)
-- rolled back a day (01-Apr-2025 was stored as 2025-03-31).
--
-- This script shifts affected period_start / period_end forward by 1 day.
--
-- !! IMPORTANT — READ BEFORE RUNNING !!
-- Only run this ONCE, and only against requests created BEFORE the frontend
-- fix was deployed. Running it twice will over-shift the dates.
-- Requests created AFTER the fix already store the correct date and must NOT
-- be shifted.
--
-- Step 1: inspect what would change (safe, read-only):
--     sudo -u postgres psql -d vlr_db -f /tmp/09_fix_period_dates.sql
--     (the script only SELECTs by default)
--
-- Step 2: after confirming the list, uncomment the UPDATE block at the bottom
--     and re-run to apply.
-- ============================================================

\connect vlr_db

-- ── Step 1: review the affected rows ──
-- Adjust the created_date cutoff to the moment you deployed the frontend fix.
\echo 'Requests that would be shifted +1 day:'

SELECT
    id,
    request_number,
    title,
    period_start                   AS current_start,
    period_start + INTERVAL '1 day' AS corrected_start,
    period_end                     AS current_end,
    period_end + INTERVAL '1 day'   AS corrected_end,
    created_date
FROM public.vlr_reconciliation_requests
WHERE created_date < '2026-07-31 00:00:00+05:30'   -- <== set to your deploy time
ORDER BY created_date;


-- ── Step 2: apply the correction (UNCOMMENT to run) ──
-- BEGIN;
--
-- UPDATE public.vlr_reconciliation_requests
-- SET period_start = period_start + INTERVAL '1 day',
--     period_end   = period_end   + INTERVAL '1 day'
-- WHERE created_date < '2026-07-31 00:00:00+05:30';  -- <== same cutoff as above
--
-- -- Verify the result before committing:
-- SELECT id, request_number, period_start, period_end
-- FROM public.vlr_reconciliation_requests
-- ORDER BY created_date;
--
-- COMMIT;   -- or ROLLBACK; if the values look wrong
