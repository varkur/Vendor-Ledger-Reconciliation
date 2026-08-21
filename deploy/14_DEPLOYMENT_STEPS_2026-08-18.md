# Deployment steps — 2026-08-18

Covers everything committed since the last deploy: user provisioning
(manual creation + Darwinbox import), the Darwin AD URL fix + IT_Admin
RBAC permission fix, CC-all-contacts on invite emails, mapping-before-
reconcile for direct dual-ledger uploads, and the reconciliation export
Remark-column fix.

Commits included: `b50aa5d`, `8fc0421`, `d27e95e`, `b4bd4be`, `cfa2729`.

Both deploy artifacts (`deploy/app`, `deploy/dist`) have already been
synced/rebuilt from the current source as part of this change — you're
copying the artifacts below, not building from `backend/`/`frontend/`
source on the server.

## 1. Back up the database (always, before any schema change)

```bash
sudo -u postgres pg_dump -d vlr_db -F c -f /tmp/vlr_db_backup_$(date +%Y%m%d_%H%M).dump
```

## 2. Stop the backend

```bash
sudo systemctl stop ledger-recon-backend.service
```

## 3. Apply database changes

Two new idempotent SQL scripts — copy them to the server and run in order:

```bash
sudo cp deploy/12_departments_group_companies_and_darwinbox.sql /tmp/
sudo cp deploy/13_fix_it_admin_permissions.sql /tmp/

# 1. Schema: departments + group_companies lookup tables, user_details FK columns
sudo -u postgres psql -d vlr_db -v ON_ERROR_STOP=1 -f /tmp/12_departments_group_companies_and_darwinbox.sql

# 2. Data fix: grant IT_Admin the users/roles/audit/rbac permissions it was missing
sudo -u postgres psql -d vlr_db -v ON_ERROR_STOP=1 -f /tmp/13_fix_it_admin_permissions.sql
```

Verify:
```bash
sudo -u postgres psql -d vlr_db -c "\d departments"
sudo -u postgres psql -d vlr_db -c "\d group_companies"
sudo -u postgres psql -d vlr_db -c "SELECT column_name FROM information_schema.columns WHERE table_name='user_details' AND column_name IN ('department_id','group_company_id');"
sudo -u postgres psql -d vlr_db -c "SELECT p.code FROM role_permissions rp JOIN roles r ON r.id=rp.role_id JOIN permissions p ON p.id=rp.permission_id WHERE r.code='IT_Admin' AND p.code LIKE 'users.%';"
```

No data migration/backfill needed — both new tables start empty and are
populated lazily by the app (get-or-create) the first time a department/
group company name is encountered.

## 4. Deploy the backend artifact

```bash
# On your side, copy the updated deploy/app/ folder to the server, e.g.:
scp -r deploy/app/* user@server:/opt/vlr/app/
```

Update `/opt/vlr/app/.env` with two new settings (see `deploy/app/.env.example`):

```
# Fallback password used when a user is created/imported without an explicit
# password. Treat as a secret.
DARWINBOX_DEFAULT_PASSWORD=<set a real value>

# Role code auto-assigned to Darwinbox-imported users. Must already exist
# (it does by default — seeded as "Reconciliation_User").
DARWINBOX_DEFAULT_ROLE_CODE=Reconciliation_User
```

**Also fix `EMPLOYEE_AD_BASE_URL` if not already correct** — a stray
`/rest-doc` path segment was breaking every Darwin AD call (login validation
+ employee import) with a 404:
```
EMPLOYEE_AD_BASE_URL=https://ad-prod-darwinsvc-prod.apps.emart.oneemcure.local/adintegratorservices/rest/v1
```
(NOT `.../rest-doc/adintegratorservices/rest/v1` — check the current value
on the server before assuming it's already fixed there.)

Install any new Python dependencies (none introduced by this change —
Hypothesis is dev/test-only, not required at runtime) and start the
service:

```bash
cd /opt/vlr/app
source .venv/bin/activate
pip install -r requirements.txt   # no new runtime deps, but harmless to re-run
sudo systemctl start ledger-recon-backend.service
sudo systemctl status ledger-recon-backend.service
```

`run.sh`/`run.ps1` calls `alembic upgrade head` automatically on startup —
it will see the DB already at `t7i8j9k0l1m2` (set by step 3) and no-op, so
this is safe even though you applied the schema via raw SQL instead of
Alembic directly.

## 5. Deploy the frontend artifact

```bash
scp -r deploy/dist/* user@server:/var/www/vlr/
```
No nginx/IIS config changes needed for this release.

## 6. Post-deploy verification

- [ ] Log in as `admin` — should be fast (no hang). If `admin` (or any
      account) is assigned `IT_Admin` and User Management previously 403'd,
      it should now load.
- [ ] User Management → "New User": form now asks for name/email/department
      (previously just username/password/role) — create a test user and
      confirm it appears in the list with those details.
- [ ] User Management → "Fetch Employee" (Darwinbox import): import a known
      employee ID and confirm it succeeds (was 502 before the
      `EMPLOYEE_AD_BASE_URL` fix) and the imported user shows up in the list.
- [ ] Direct Reconciliation → "New Reconciliation": upload both ledger
      files — you should land on the case's mapping page instead of the
      matching engine running immediately. Confirm "Start Reconciliation"
      still works from there.
- [ ] Send Vendor Invites: confirm the invite email now CC's every other
      contact on the vendor record, not just the one picked in the UI.
- [ ] Reconciliation export (any case): open the "Reconciliation" sheet and
      confirm the **Remark** column is now populated for Reversal Entries
      and "Date Range and Amount Matched" rows (previously blank).

## 7. Rollback plan

If something goes wrong:
```bash
sudo systemctl stop ledger-recon-backend.service
sudo -u postgres pg_restore -d vlr_db --clean /tmp/vlr_db_backup_<timestamp>.dump
# restore the previous deploy/app and deploy/dist from your last known-good backup/tag
sudo systemctl start ledger-recon-backend.service
```
The schema changes here are purely additive (new tables + nullable FK
columns + new role_permissions rows) — nothing in step 3 destroys or
alters existing data, so a straight DB restore is not strictly required
unless something else goes wrong; stopping the service and reverting the
`app`/`dist` folders alone is usually sufficient.
