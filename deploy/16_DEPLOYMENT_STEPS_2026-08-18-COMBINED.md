# COMBINED Deployment Steps — everything since your last deploy (Aug 13)

Your last live deploy was Aug 13. Nothing has gone out since — so this is
**one deployment covering 6 commits**, not just today's frontend tweak:

| Commit | Date | What |
|---|---|---|
| `e4942f1` | Aug 14 | Consolidated ledger auto-detect + PAN split fixes (**new table**: `vlr_ledger_upload_staging`) |
| `b50aa5d` | Aug 17 | User provisioning: manual user creation + Darwinbox import (**new tables**: `departments`, `group_companies`; **new columns** on `user_details`) |
| `8fc0421` | Aug 17 | Fix Darwin AD base URL (was 404'ing) + missing IT_Admin RBAC permissions (**data fix**, no schema) |
| `d27e95e` | Aug 17 | CC all vendor contacts on reconciliation invite emails (code only) |
| `b4bd4be` | Aug 17 | Require column mapping before reconciling direct dual-ledger uploads (code only) |
| `cfa2729` | Aug 17 | Auto-populate Remark column in reconciliation export (code only) |
| *(uncommitted, today)* | Aug 18 | Mapping popup UX, single Submit button, Party Code auto-fill on both ledger sides (frontend only) |

**Two DB migrations need raw SQL** (`12_...sql` for departments/group
companies, `15_add_ledger_upload_staging.sql` for the staging table — the
latter was missing until just now, I found the gap while preparing this).
One **data-only fix** (`13_...sql` for IT_Admin permissions). Everything
else is app-code, no schema impact.

Today's frontend changes (mapping popup, party code, submit button) are
**not committed yet** — see step 0.

---

## 0. Commit today's frontend changes (do this first)

```bash
git add frontend/src/features/direct-reconciliation/pages/DirectReconciliationPage.tsx
git add frontend/src/features/track-reconciliation/pages/ColumnMappingPage.tsx
git add frontend/src/features/track-reconciliation/pages/MappingFormPage.tsx
git add frontend/src/features/track-reconciliation/components/MappingFormContent.tsx
git commit -m "Convert column mapping to popup style, fix duplicate submit, autofill party code on both ledger sides"
```

(The `deploy/12`, `deploy/13`, `deploy/app/.env.example` files are already
staged from earlier — commit those too, or fold into the same commit.)

## 1. Back up the database (mandatory — this deploy has schema changes)

```bash
sudo -u postgres pg_dump -d vlr_db -F c -f /tmp/vlr_db_backup_$(date +%Y%m%d_%H%M).dump
```

## 2. Stop the backend

```bash
sudo systemctl stop ledger-recon-backend.service
```

## 3. Apply database changes — IN THIS ORDER

```bash
sudo cp deploy/12_departments_group_companies_and_darwinbox.sql /tmp/
sudo cp deploy/13_fix_it_admin_permissions.sql /tmp/
sudo cp deploy/15_add_ledger_upload_staging.sql /tmp/

# 1. New table: vlr_ledger_upload_staging (consolidated multi-vendor upload) — Aug 14 change
sudo -u postgres psql -d vlr_db -v ON_ERROR_STOP=1 -f /tmp/15_add_ledger_upload_staging.sql

# 2. New tables: departments + group_companies, new FK columns on user_details
sudo -u postgres psql -d vlr_db -v ON_ERROR_STOP=1 -f /tmp/12_departments_group_companies_and_darwinbox.sql

# 3. Data fix: grant IT_Admin the users/roles/audit/rbac permissions it was missing
sudo -u postgres psql -d vlr_db -v ON_ERROR_STOP=1 -f /tmp/13_fix_it_admin_permissions.sql
```

Verify:
```bash
sudo -u postgres psql -d vlr_db -c "\d vlr_ledger_upload_staging"
sudo -u postgres psql -d vlr_db -c "\d departments"
sudo -u postgres psql -d vlr_db -c "\d group_companies"
sudo -u postgres psql -d vlr_db -c "SELECT column_name FROM information_schema.columns WHERE table_name='user_details' AND column_name IN ('department_id','group_company_id');"
sudo -u postgres psql -d vlr_db -c "SELECT p.code FROM role_permissions rp JOIN roles r ON r.id=rp.role_id JOIN permissions p ON p.id=rp.permission_id WHERE r.code='IT_Admin' AND p.code LIKE 'users.%';"
```

No backfill needed for any of the three — all new tables/columns start
empty or nullable and get populated lazily by the app.

## 4. Deploy the backend artifact

`deploy/app/src` is already synced with `backend/src` (verified — 0 diff).
Copy it over:

```bash
scp -r deploy/app/* user@server:/opt/vlr/app/
```

**Update `/opt/vlr/app/.env` on the server** — add/fix these (see
`deploy/app/.env.example`):

```
# Fallback password used when a user is created/imported without an explicit
# password. TREAT AS A SECRET — set a real value, not the placeholder below.
DARWINBOX_DEFAULT_PASSWORD=<set a real value>

# Role auto-assigned to Darwinbox-imported users. Must already exist —
# it will after step 3/5 (seeded as "Reconciliation_User").
DARWINBOX_DEFAULT_ROLE_CODE=Reconciliation_User
```

**Fix `EMPLOYEE_AD_BASE_URL`** if the server still has the broken value —
check the current value first, don't assume:
```
EMPLOYEE_AD_BASE_URL=https://ad-prod-darwinsvc-prod.apps.emart.oneemcure.local/adintegratorservices/rest/v1
```
(NOT `.../rest-doc/adintegratorservices/rest/v1` — that stray `/rest-doc`
segment 404'd every Darwin AD call.)

## 5. Run the RBAC seed script (new roles/permissions)

This is idempotent (skips anything already present) and also **fails
loudly** if `DARWINBOX_DEFAULT_ROLE_CODE` doesn't resolve to a real role —
so run it and read the output:

```bash
cd /opt/vlr/app
source .venv/bin/activate
pip install -r requirements.txt   # no new runtime deps this round, harmless to re-run
python -m scripts.seed_rbac
```

Confirm it prints `✓ RBAC seed complete.` and `✓ Verified
DARWINBOX_DEFAULT_ROLE_CODE=...`. If it raises `RuntimeError` about the
role not resolving, fix the `.env` value or check step 3 ran.

## 6. Start the backend

```bash
sudo systemctl start ledger-recon-backend.service
sudo systemctl status ledger-recon-backend.service
```

`run.sh`/`run.ps1` calls `alembic upgrade head` on startup — it'll see the
DB already at the latest revision (from step 3's raw SQL) and no-op.

## 7. Deploy the frontend artifact

`deploy/dist` is already rebuilt from current source, including today's
mapping-popup + party-code changes:

```bash
scp -r deploy/dist/* user@server:/var/www/vlr/
```

## 8. Post-deploy verification — go through ALL of these, not just today's

**User Management (new this deploy):**
- [ ] Log in as an IT_Admin-assigned user — User Management should load
      (previously 403'd before the RBAC fix).
- [ ] User Management → "New User": form asks for name/email/department/
      designation/reporting manager, password optional. Create a test user,
      confirm it appears in the list with those fields populated.
- [ ] User Management → "Fetch Employee" (Darwinbox import): import a
      known employee ID — should succeed (was 502 before the AD URL fix).
      Confirm the imported user appears with correct department/RBAC role.

**Consolidated ledger upload (Aug 14 change):**
- [ ] Try the consolidated multi-vendor company ledger upload flow (if
      exposed in the UI) — confirm it doesn't error on a missing table.

**Reconciliation flow (Aug 17 changes):**
- [ ] Direct Reconciliation → "New Reconciliation": upload both ledgers —
      mapping form opens as a **popup**, not a page redirect.
- [ ] Party Code is pre-filled on **both** company and vendor mapping
      forms (read-only, green check).
- [ ] Only **one** Submit button on the mapping form.
- [ ] Submitting company mapping chains straight into vendor mapping popup.
- [ ] "Map" buttons on an existing case's summary page also open the popup.
- [ ] Send Vendor Invites: confirm the email now CC's every contact on the
      vendor record, not just the one picked in the UI.
- [ ] Reconciliation export: confirm the **Remark** column is populated for
      Reversal Entries and "Date Range and Amount Matched" rows.

## 9. Rollback plan

```bash
sudo systemctl stop ledger-recon-backend.service
sudo -u postgres pg_restore -d vlr_db --clean /tmp/vlr_db_backup_<timestamp>.dump
# restore the previous deploy/app and deploy/dist from your last known-good backup/tag
sudo systemctl start ledger-recon-backend.service
```
All three schema changes (steps 3) are purely additive — new tables,
nullable FK columns, new role_permissions rows — nothing destroys existing
data. A straight restore of `app`/`dist` folders + service restart is
usually enough; full DB restore is your safety net if something else goes
wrong.
