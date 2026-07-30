-- ============================================================
-- 06_backfill_request_numbers.sql
-- Assigns request_number to EXISTING reconciliation requests that don't
-- have one yet, using the pattern "{company_code}-{5-digit serial}".
--
-- Serial is assigned per company_code, ordered by created_date (oldest = 1),
-- and continues past any request_numbers already present for that code so
-- there are no collisions with rows created by the app after the upgrade.
--
-- Run AFTER 05_request_columns.sql:
--     sudo -u postgres psql -d vlr_db -v ON_ERROR_STOP=1 -f /tmp/06_backfill_request_numbers.sql
--
-- Idempotent: only rows with a NULL/blank request_number are touched.
-- ============================================================

\connect vlr_db

WITH
-- Highest serial already used per company_code (from rows that already have
-- a request_number), so the backfill continues from there.
existing_max AS (
    SELECT
        company_code,
        COALESCE(
            MAX(
                CASE
                    WHEN request_number ~ ('^' || company_code || '-[0-9]+$')
                    THEN CAST(split_part(request_number, '-', 2) AS INTEGER)
                    ELSE 0
                END
            ),
            0
        ) AS max_serial
    FROM public.vlr_reconciliation_requests
    WHERE request_number IS NOT NULL AND request_number <> ''
    GROUP BY company_code
),
-- Rows needing a number, numbered sequentially per company_code by age.
to_fill AS (
    SELECT
        r.id,
        r.company_code,
        ROW_NUMBER() OVER (
            PARTITION BY r.company_code
            ORDER BY r.created_date ASC, r.id ASC
        ) AS rn
    FROM public.vlr_reconciliation_requests r
    WHERE r.request_number IS NULL OR r.request_number = ''
)
UPDATE public.vlr_reconciliation_requests AS req
SET request_number =
        UPPER(tf.company_code) || '-' ||
        LPAD((COALESCE(em.max_serial, 0) + tf.rn)::text, 5, '0')
FROM to_fill tf
LEFT JOIN existing_max em ON em.company_code = tf.company_code
WHERE req.id = tf.id;

-- Report how many now have a number (sanity check).
-- SELECT company_code, count(*) FILTER (WHERE request_number IS NOT NULL) AS numbered,
--        count(*) AS total
-- FROM public.vlr_reconciliation_requests GROUP BY company_code;
