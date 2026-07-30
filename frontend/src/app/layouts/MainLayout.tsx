/**
 * Main application layout — Emcure light theme (Sakai-style).
 * Light sidebar using PrimeReact PanelMenu for nested navigation:
 * - Dashboard
 * - Account Reco (Manage Party, Request Statement, ...)
 * - Settings (Manage Users, Company Profile, ...)
 * - Utilities (Audit Logs, ERP Integration, Automation)
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { PanelMenu } from 'primereact/panelmenu';
import { Menu } from 'primereact/menu';
import { Avatar } from 'primereact/avatar';
import type { MenuItem } from 'primereact/menuitem';
import { useAppSelector, useAppDispatch } from '@app/store';
import { fetchEntities, selectEntity, type CompanyEntity } from '@app/store/entitySlice';
import { logout } from '@features/authentication/store/authSlice';
import { useQueryClient } from '@tanstack/react-query';

interface NavLeaf {
  label: string;
  icon?: string;
  path: string;
}

interface NavGroup {
  label: string;
  icon: string;
  path?: string;
  children?: NavLeaf[];
}

const navModel: NavGroup[] = [
  {
    label: 'Dashboard',
    icon: 'pi pi-home',
    path: '/dashboard',
  },
  {
    label: 'Account Reco',
    icon: 'pi pi-sync',
    children: [
      { label: 'Manage Party', path: '/manage-party' },
      { label: 'Request Statement', path: '/request-statement' },
      { label: 'Direct Reconciliation', path: '/direct-reconciliation' },
      { label: 'Track Reconciliation', path: '/track-reconciliation' },
      { label: 'Exceptions', path: '/exceptions' },
      { label: 'Approvals', path: '/approvals' },
      { label: 'Reports', path: '/reports' },
      { label: 'Notifications', path: '/notifications' },
    ],
  },
  {
    label: 'Settings',
    icon: 'pi pi-cog',
    children: [
      { label: 'Manage Users', path: '/access-management/roles' },
      { label: 'Company Profile', path: '/settings/company-profile' },
      { label: 'Email Templates', path: '/settings/email-templates' },
      { label: 'Document Types', path: '/settings/document-types' },
      { label: 'Reminders', path: '/settings/reminders' },
      { label: 'Email Config', path: '/settings/email-config' },
      { label: 'Workflow Config', path: '/settings/workflow-definitions' },
    ],
  },
  {
    label: 'Utilities',
    icon: 'pi pi-wrench',
    children: [
      { label: 'Audit Logs', path: '/access-management/audit-logs' },
      { label: 'ERP Integration', path: '/erp-integration' },
      { label: 'Automation', path: '/automation' },
    ],
  },
];

export const MainLayout = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const dispatch = useAppDispatch();
  const queryClient = useQueryClient();
  const { user } = useAppSelector((state) => state.auth);
  const { entities, selectedEntity } = useAppSelector((state) => state.entity);

  const userMenu = useRef<Menu>(null);
  const entityMenu = useRef<Menu>(null);

  // Load entities on mount
  useEffect(() => {
    dispatch(fetchEntities());
  }, [dispatch]);

  const isActive = (path: string) =>
    location.pathname === path || location.pathname.startsWith(path + '/');

  const handleEntityChange = (entity: CompanyEntity) => {
    dispatch(selectEntity(entity));
    queryClient.invalidateQueries();
  };

  // Controlled expansion so clicking a sub-item doesn't collapse/re-open the
  // panel. Initialise with the group that contains the current route expanded.
  const [expandedKeys, setExpandedKeys] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    navModel.forEach((group) => {
      if (group.children?.some((c) => isActive(c.path))) {
        initial[group.label] = true;
      }
    });
    return initial;
  });

  // Build PanelMenu model. Stable except for the active-highlight className,
  // which depends on the current path. Expansion is controlled separately via
  // expandedKeys, so re-rendering the model does not re-animate the panels.
  const panelModel: MenuItem[] = useMemo(
    () =>
      navModel.map((group) => {
        if (!group.children) {
          return {
            key: group.label,
            label: group.label,
            icon: group.icon,
            className: isActive(group.path!) ? 'em-menu-active' : undefined,
            command: () => navigate(group.path!),
          };
        }
        return {
          key: group.label,
          label: group.label,
          icon: group.icon,
          items: group.children.map((child) => ({
            key: child.path,
            label: child.label,
            icon: child.icon,
            className: isActive(child.path) ? 'em-menu-active' : undefined,
            command: () => navigate(child.path),
          })),
        };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [location.pathname]
  );

  const userMenuItems: MenuItem[] = [
    { label: user?.username || 'User', icon: 'pi pi-user', disabled: true },
    { separator: true },
    {
      label: 'Logout',
      icon: 'pi pi-sign-out',
      command: () => {
        dispatch(logout());
        navigate('/login');
      },
    },
  ];

  const entityMenuItems: MenuItem[] = entities.map((entity) => ({
    label: entity.name,
    icon: entity.id === selectedEntity?.id ? 'pi pi-check' : undefined,
    command: () => handleEntityChange(entity),
  }));

  return (
    <div className="min-h-screen flex" style={{ background: 'var(--color-surface-ground)' }}>
      {/* ─── Sidebar ─── */}
      <aside className="em-sidebar" aria-label="Sidebar navigation">
        {/* Logo */}
        <div className="em-sidebar-logo">
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #ff4d54, #b00e14)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <i className="pi pi-refresh" style={{ color: '#fff', fontSize: 14 }} />
          </div>
          <span className="logo-text">EMCURE VLR</span>
        </div>

        {/* Navigation — PrimeReact PanelMenu (controlled expansion) */}
        <nav className="em-sidebar-nav">
          <PanelMenu
            model={panelModel}
            multiple
            className="em-panelmenu"
            expandedKeys={expandedKeys}
            onExpandedKeysChange={(keys) => setExpandedKeys(keys as Record<string, boolean>)}
          />
        </nav>
      </aside>

      {/* ─── Main Content ─── */}
      <div className="flex-1 flex flex-column em-main-content" style={{ minWidth: 0 }}>
        {/* Top Bar */}
        <header className="em-topbar" aria-label="Top bar">
          <div className="em-topbar-left">
            <i className="pi pi-question-circle" style={{ fontSize: 18, color: 'var(--color-text-muted)' }} />

            {/* Entity selector */}
            <Menu model={entityMenuItems} popup ref={entityMenu} />
            <button
              className="em-company-selector"
              style={{ cursor: 'pointer', background: 'var(--color-surface)' }}
              onClick={(e) => entityMenu.current?.toggle(e)}
              aria-haspopup="true"
            >
              <span>{selectedEntity?.name || 'Select Entity'}</span>
              <i className="pi pi-chevron-down" style={{ fontSize: 10 }} />
            </button>
          </div>

          <div className="em-topbar-right">
            <Menu model={userMenuItems} popup ref={userMenu} />
            <button
              onClick={(e) => userMenu.current?.toggle(e)}
              aria-label="User menu"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                background: 'none',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              <span className="em-user-info">{user?.username || 'User'}</span>
              <Avatar
                label={(user?.username?.charAt(0) || 'U').toUpperCase()}
                shape="circle"
                size="normal"
                style={{
                  background: 'var(--color-primary)',
                  color: '#fff',
                  width: '2rem',
                  height: '2rem',
                  fontSize: '0.8rem',
                }}
              />
            </button>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-y-auto" style={{ padding: '24px' }}>
          <Outlet />
        </main>
      </div>
    </div>
  );
};
