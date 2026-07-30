# Deployment — Vendor Ledger Reconciliation (PAM server)

Two independent artifacts so you can deploy the frontend and backend separately:

```
deploy/
├── app/                 # BACKEND artifact (FastAPI)
│   ├── src/             # application code
│   ├── scripts/         # ops/maintenance scripts
│   ├── requirements.txt # runtime dependencies
│   ├── alembic.ini      # migrations config
│   ├── run.sh / run.ps1 # start scripts (migrate + uvicorn)
│   └── .env.example     # copy to app/.env and fill in
│
├── dist/                # FRONTEND artifact (built React SPA — static files)
│
├── nginx.conf.example   # serve dist + reverse-proxy /api to the backend
├── requirements.txt     # (same as app/requirements.txt, for convenience)
└── README.md
```

The frontend calls the API using the **relative path `/api/v1`**. The simplest,
CORS-free setup is to serve `dist` from a web server (Nginx/IIS) that reverse
proxies `/api` to the backend `app`. See `nginx.conf.example`.

---

## Backend (`app`)

Requirements: Python 3.12+, PostgreSQL reachable via `DATABASE_URL`.

1. Copy the folder to the server, e.g. `/opt/vlr/app`.
2. Create a virtualenv and install deps:
   ```bash
   cd /opt/vlr/app
   python3.12 -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Configure env: copy `.env.example` to `.env`, set `DATABASE_URL`,
   `JWT_SECRET_KEY`, `ENCRYPTION_KEY`, SMTP settings, and `CORS_ORIGINS`.
4. Start (runs `alembic upgrade head` then uvicorn):
   ```bash
   bash run.sh                    # Linux
   # or
   powershell -File run.ps1       # Windows
   ```
   The API listens on `0.0.0.0:8000` by default (`HOST`/`PORT`/`WEB_CONCURRENCY`).

   For a managed service, use systemd (Linux) or NSSM / Windows Service to run
   `uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4` with
   `PYTHONPATH` set to the `app` directory.

Verify: `http://<server>:8000/docs`.

---

## Frontend (`dist`)

`dist` is plain static files. Serve them with Nginx (Linux) or IIS (Windows).

### Nginx (recommended)
1. Copy `dist/` to `/var/www/vlr`.
2. Copy `nginx.conf.example` to `/etc/nginx/sites-available/vlr`, edit
   `server_name`, `root`, and the `proxy_pass` backend address.
3. Enable and reload:
   ```bash
   ln -s /etc/nginx/sites-available/vlr /etc/nginx/sites-enabled/vlr
   nginx -t && systemctl reload nginx
   ```

### IIS (Windows)
- Point a site at the `dist` folder.
- Add URL Rewrite rules: SPA fallback to `index.html`, and reverse proxy
  (ARR) for `/api/*` → `http://127.0.0.1:8000`.

---

## Rebuilding the frontend
`dist` is a snapshot. To refresh after frontend changes:
```bash
cd frontend
npx vite build          # use vite build, not `npm run build`
# copy frontend/dist -> deploy/dist
```
(`npm run build` runs a strict `tsc` type-check with pre-existing, non-blocking
errors; `npx vite build` produces the same runtime bundle.)

## Notes
- **CORS**: not needed when `/api` is proxied from the same origin as `dist`.
  If you host the frontend and backend on different origins, set
  `CORS_ORIGINS` in the backend `.env` to the frontend's URL.
- **Uploads**: allow large request bodies at the proxy (`client_max_body_size`)
  for ledger file uploads.
- **Secrets**: generate `ENCRYPTION_KEY` with
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
  and use a strong `JWT_SECRET_KEY`.

---

## Rebuilding the database from scratch (fresh install)

If you need to (re)create the database with schema + basic seed data (admin
user, RBAC roles/permissions, SLA configs), do this on the server:

### 1. Create an empty database and app user (run once, as a Postgres superuser)
```sql
CREATE DATABASE vendor_portal;
CREATE USER vendor_app_user WITH PASSWORD 'VendorSecure2026';
GRANT ALL PRIVILEGES ON DATABASE vendor_portal TO vendor_app_user;
-- On PostgreSQL 15+, also grant schema rights:
\c vendor_portal
GRANT ALL ON SCHEMA public TO vendor_app_user;
```

> To wipe an existing DB and start over:
> `DROP DATABASE vendor_portal;` then recreate as above. This deletes ALL data.

### 2. Point the app at the database
In `app/.env` set (note the **+asyncpg** async driver — required by the app):
```
DATABASE_URL=postgresql+asyncpg://vendor_app_user:VendorSecure2026@localhost:5432/vendor_portal
```
(The plain `postgresql://...` form is only for the `psql` CLI, not the app.)

### 3. Run the one-shot bootstrap (migrations + seed data)
```bash
cd /opt/vlr/app          # the backend artifact
export PYTHONPATH="$PWD"
python -m scripts.bootstrap_db
```
This will:
1. `alembic upgrade head` — create all tables
2. seed the default **admin** user  (login: `admin` / `Admin@123!`)
3. seed RBAC permissions + VLR roles (IT_Admin, Reconciliation_Manager, etc.)
4. assign the admin user full VLR access
5. seed default SLA durations

Everything is idempotent — safe to re-run. **Change the admin password after
first login.**

### 4. Vendor / party master data
Vendors (parties) are not seeded — import them through the UI:
**Manage Party → Import**, using the `Party_Import_Template` (CSV/Excel).
The importer truncates over-length values to DB column limits and reports
per-row errors.
