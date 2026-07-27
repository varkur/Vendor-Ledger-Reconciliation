# Database setup via SQL scripts (no Python / asyncpg needed)

Use these SQL files to build the `vlr_db` database with schema and seed data
directly through `psql` — no app dependencies required.

Files (run in this order):
1. `00_create_database.sql` — drops & recreates the DB (`vlr_db`), app user (`vlr_user`), extension
2. `01_schema.sql`          — creates all tables, indexes, constraints
3. `02_seed_data.sql`       — inserts seed data (admin user, roles, permissions, SLA)
4. `03_grant_privileges.sql`— grants/reassigns object ownership to `vlr_user`

## Upload the files to the server
Copy all four `.sql` files to a directory the `postgres` user can read, e.g.
`/tmp` (avoid `/home/<user>` — postgres often can't read there, which causes
`Permission denied`).

```bash
sudo cp *.sql /tmp/
```

## Run them

```bash
# 1. Create database + user + extension (as postgres superuser)
#    WARNING: this DROPS vlr_db and deletes all its data.
sudo -u postgres psql -f /tmp/00_create_database.sql

# 2. Load the schema (all tables)
sudo -u postgres psql -d vlr_db -v ON_ERROR_STOP=1 -f /tmp/01_schema.sql

# 3. Load the seed data
sudo -u postgres psql -d vlr_db -v ON_ERROR_STOP=1 -f /tmp/02_seed_data.sql

# 4. Grant privileges / reassign ownership to the app user
sudo -u postgres psql -d vlr_db -v ON_ERROR_STOP=1 -f /tmp/03_grant_privileges.sql
```

## Verify
```bash
sudo -u postgres psql -d vlr_db -c "\dt"                          # tables exist
sudo -u postgres psql -d vlr_db -c "SELECT username FROM users;"  # -> admin
sudo -u postgres psql -d vlr_db -c "SELECT count(*) FROM permissions;"  # -> 65
# confirm app user can write:
sudo -u postgres psql -d vlr_db -c "SELECT has_table_privilege('vlr_user','vlr_vendors','INSERT');"  # -> t
```

## Restart the backend
```bash
sudo systemctl restart ledger-recon-backend.service
sudo systemctl status ledger-recon-backend.service
```

## Login after setup
- Username: `admin`
- Password: `Admin@123`
- Change the password after first login.

## Notes
- Seed data included: 1 admin user, 7 roles, 65 permissions, role-permission
  mappings, SLA configurations, and the alembic version marker (so the app's
  `alembic upgrade head` will see the DB as already up to date).
- Vendor/party master data is NOT seeded — import it via the UI
  (Manage Party -> Import) after logging in.
- `02_seed_data.sql` sets `session_replication_role = replica` during load to
  handle the self-referential FK on `roles`; it resets to default at the end.
- Because the schema/seed load runs as the postgres superuser, objects are owned
  by postgres. `03_grant_privileges.sql` reassigns ownership to `vlr_user` so the
  app (which connects as `vlr_user`) can read/write. Do not skip step 4.
- The app's `.env` runtime driver:
  `DATABASE_URL=postgresql+asyncpg://vlr_user:vlr_pass@localhost:5432/vlr_db`
