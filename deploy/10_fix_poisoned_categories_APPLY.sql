-- ============================================================
-- 10_fix_poisoned_categories_APPLY.sql
-- APPLY version — Step 2 is already uncommented. Run this ONLY after you
-- have reviewed the dry-run report from 10_fix_poisoned_categories.sql
-- and taken a backup (pg_dump -t vlr_ledger_entries).
--
-- Clears raw/unrecognized document_category values on vlr_ledger_entries
-- back to NULL so the reconciliation engine can re-derive them correctly
-- via the fixed DEFAULT_DOC_TYPE_MAP.
--
-- Confirmed by the dry-run against this DB: 374 rows across 5 cases
-- (RV, DZ, REC, INV, TDS, CM, Purchase Voucher - R, REFUND).
--
-- Safe to re-run (idempotent) — only clears values not already in the
-- recognized standard category set.
-- ============================================================

\connect vlr_db

BEGIN;

UPDATE public.vlr_ledger_entries
SET document_category = NULL
WHERE document_category IS NOT NULL
  AND document_category <> ''
  AND document_category NOT IN (
      'Invoice', 'Payment', 'Debit Note', 'Credit Note', 'Receipt',
      'TDS Adjusted', 'Opening Balance', 'Closing Balance',
      'Knocking Off', 'Adjusted', 'Journal', 'Other', 'Unknown'
  );

-- Verify the result before committing:
\echo 'document_category distribution AFTER clearing:'
SELECT document_category, count(*) FROM public.vlr_ledger_entries
GROUP BY document_category ORDER BY count(*) DESC;

COMMIT;

\echo 'Done. Now re-run reconciliation for every affected case (RV/DZ/REC/INV/TDS/CM/REFUND cases) so match counts update.'
