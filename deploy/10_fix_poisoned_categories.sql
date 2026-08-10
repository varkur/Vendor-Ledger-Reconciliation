-- ============================================================
-- 10_fix_poisoned_categories.sql
-- Clears raw/unrecognized document_category values on vlr_ledger_entries
-- so they can be re-derived correctly by the reconciliation engine.
--
-- CAUSE: an old (already-removed) code path stored the raw SAP/Tally
-- document type code (e.g. 'RV', 'DZ', 'REC', 'INV', 'CM', 'REFUND')
-- directly into document_category instead of mapping it to a standard
-- category (Invoice, Payment, etc). Because the app intentionally never
-- overwrites a non-empty document_category (to preserve user-mapped
-- values from the Map Document Type screen), these poisoned rows never
-- self-heal even after the mapping/category-gating fixes were deployed.
-- This made "Invoice" vs raw-code categories look incompatible to the
-- engine's category-gating logic, collapsing the match count.
--
-- This script does NOT touch the mapping logic — it only clears the bad
-- values back to NULL so the next reconciliation run re-derives them
-- through the (now-fixed) DEFAULT_DOC_TYPE_MAP.
--
-- !! IMPORTANT — READ BEFORE RUNNING !!
-- 1. This is a bulk UPDATE. Take a backup / confirm you have a recent one
--    before running Step 2 (e.g. pg_dump -d vlr_db -t vlr_ledger_entries).
-- 2. This script is idempotent — safe to re-run, it only clears values
--    that are NOT already one of the recognized standard categories.
-- 3. After running Step 2, you MUST re-run reconciliation for any
--    affected case (UI "Start Reconciliation", or the equivalent script)
--    for match counts to update. Clearing the column alone does not
--    recompute matches.
--
-- Step 1: inspect what would change (safe, read-only — this is all this
--    script does by default):
--     sudo -u postgres psql -d vlr_db -f /tmp/10_fix_poisoned_categories.sql
--
-- Step 2: after reviewing the report, uncomment the UPDATE block at the
--    bottom and re-run to apply.
-- ============================================================

\connect vlr_db

-- Recognized standard categories (must match STANDARD_CATEGORIES /
-- WILDCARD_CATEGORIES in backend/src/domain/services/vlr/doc_type_mapping.py
-- and reconciliation_engine_service.py as of this fix). NULL and '' are
-- always fine (they mean "not yet classified", handled as wildcard).
-- If you add new categories to that Python list later, add them here too.

-- ── Step 1a: category distribution across all ledger entries ──
\echo 'Current document_category distribution:'

SELECT
    document_category,
    count(*) AS row_count
FROM public.vlr_ledger_entries
GROUP BY document_category
ORDER BY row_count DESC;

-- ── Step 1b: rows that WOULD be cleared (raw/unrecognized codes) ──
\echo 'Rows with an unrecognized document_category (would be cleared to NULL):'

SELECT
    case_id,
    document_category,
    count(*) AS row_count
FROM public.vlr_ledger_entries
WHERE document_category IS NOT NULL
  AND document_category <> ''
  AND document_category NOT IN (
      'Invoice', 'Payment', 'Debit Note', 'Credit Note', 'Receipt',
      'TDS Adjusted', 'Opening Balance', 'Closing Balance',
      'Knocking Off', 'Adjusted', 'Journal', 'Other', 'Unknown'
  )
GROUP BY case_id, document_category
ORDER BY case_id, row_count DESC;


-- ── Step 2: apply the fix (UNCOMMENT to run) ──
-- BEGIN;
--
-- UPDATE public.vlr_ledger_entries
-- SET document_category = NULL
-- WHERE document_category IS NOT NULL
--   AND document_category <> ''
--   AND document_category NOT IN (
--       'Invoice', 'Payment', 'Debit Note', 'Credit Note', 'Receipt',
--       'TDS Adjusted', 'Opening Balance', 'Closing Balance',
--       'Knocking Off', 'Adjusted', 'Journal', 'Other', 'Unknown'
--   );
--
-- -- Verify the result before committing:
-- SELECT document_category, count(*) FROM public.vlr_ledger_entries
-- GROUP BY document_category ORDER BY count(*) DESC;
--
-- COMMIT;   -- or ROLLBACK; if the values look wrong
--
-- -- After COMMIT, re-run reconciliation for every affected case so the
-- -- match counts actually update (clearing the column does not recompute
-- -- matches by itself).
</content>
