-- ============================================================
-- 13_fix_it_admin_permissions.sql
-- Fixes a seeding gap: the IT_Admin role ("VLR IT administrator with full
-- system settings access") was missing every users.*/roles.*/audit.read/
-- rbac.* permission, causing 403s on GET /api/v1/users (and related
-- user-management endpoints) for any account assigned that role.
--
-- Grants the missing permissions to IT_Admin. Idempotent — safe to re-run
-- (ON CONFLICT DO NOTHING); does nothing if the permissions are already
-- linked.
--
--     sudo -u postgres psql -d vlr_db -v ON_ERROR_STOP=1 -f /tmp/13_fix_it_admin_permissions.sql
--
-- No backend restart required (RBAC is evaluated per-request from the DB).
-- ============================================================

\connect vlr_db

-- NOTE: role_permissions has NO unique constraint on (role_id, permission_id)
-- (matches the app's own seed_rbac.py, which does its own existence check
-- instead of relying on a DB constraint) — so "ON CONFLICT DO NOTHING" would
-- silently do nothing to prevent duplicates on a re-run. Use an explicit
-- NOT EXISTS guard instead so this script is genuinely idempotent.
INSERT INTO public.role_permissions (id, role_id, permission_id, created_by, created_date, modified_by, modified_date)
SELECT
    gen_random_uuid(),
    r.id,
    p.id,
    'deploy_script',
    now(),
    'deploy_script',
    now()
FROM public.roles r
JOIN public.permissions p ON p.code IN (
    'menu.users', 'menu.roles', 'menu.audit_logs',
    'users.list', 'users.create', 'users.update', 'users.delete',
    'users.export', 'users.import',
    'roles.list', 'roles.create', 'roles.update', 'roles.assign',
    'audit.read', 'rbac.read', 'rbac.create', 'rbac.update'
)
WHERE r.code = 'IT_Admin'
  AND NOT EXISTS (
      SELECT 1 FROM public.role_permissions rp
      WHERE rp.role_id = r.id AND rp.permission_id = p.id
  );

-- Verify: IT_Admin should now show all 17 of the above permission codes.
\echo 'IT_Admin users/roles/audit/rbac permissions:'
SELECT p.code
FROM public.role_permissions rp
JOIN public.roles r ON r.id = rp.role_id
JOIN public.permissions p ON p.id = rp.permission_id
WHERE r.code = 'IT_Admin'
  AND p.code ~ '^(menu\.(users|roles|audit_logs)|users\.|roles\.|audit\.read|rbac\.)'
ORDER BY p.code;
