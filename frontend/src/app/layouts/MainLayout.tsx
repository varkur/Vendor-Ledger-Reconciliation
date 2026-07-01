/**
 * Main application layout — Sakai-style with Emcure branding.
 * Collapsible sidebar, topbar with profile menu, breadcrumbs.
 */

import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Button } from 'primereact/button';
import { Avatar } from 'primereact/avatar';
import { Menu } from 'primereact/menu';
import { Badge } from 'primereact/badge';
import { Tooltip } from 'primereact/tooltip';
import { useRef } from 'react';
import { useAppDispatch, useAppSelector } from '@app/store';
import { logout } from '@features/authentication/store/authSlice';
import { useMenuPermissions } from '@core/rbac/usePermissions';

interface NavItem {
  label: string;
  icon: string;
  path: string;
  visible?: boolean;
  section?: string;
  menuKey?: string;
}

export const MainLayout = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAppSelector((state) => state.auth);
  const userMenu = useRef<Menu>(null);
  const { menuKeys, isLoaded: rbacLoaded } = useMenuPermissions();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const navItems: NavItem[] = [
    { label: 'Dashboard', icon: 'pi pi-th-large', path: '/dashboard', section: 'Main', menuKey: 'dashboard' },
    { label: 'Commission Claims', icon: 'pi pi-wallet', path: '/claims', section: 'Main', menuKey: 'dashboard' },
    { label: 'Orders', icon: 'pi pi-list', path: '/orders', section: 'Main' },
    { label: 'Reports', icon: 'pi pi-chart-bar', path: '/reports', section: 'Main', menuKey: 'reports' },
    { label: 'Inventory', icon: 'pi pi-box', path: '/inventory', section: 'Main' },
    { label: 'Users', icon: 'pi pi-users', path: '/users', section: 'Management', menuKey: 'users' },
    { label: 'Roles & Permissions', icon: 'pi pi-shield', path: '/roles', section: 'Management', menuKey: 'roles' },
    { label: 'Audit Logs', icon: 'pi pi-history', path: '/audit-logs', section: 'Management', menuKey: 'audit_logs' },
    { label: 'Workflows', icon: 'pi pi-sitemap', path: '/workflows', section: 'Workflow', menuKey: 'workflows' },
    { label: 'Approval Matrix', icon: 'pi pi-check-square', path: '/approval-matrix', section: 'Workflow', menuKey: 'workflows' },
    { label: 'Settings', icon: 'pi pi-cog', path: '/settings', section: 'Management', menuKey: 'settings' },
    { label: 'Employee AD', icon: 'pi pi-id-card', path: '/services/employee-ad', section: 'Services', menuKey: 'services' },
  ];

  // Filter items based on RBAC menu permissions
  const visibleItems = navItems.filter((item) => {
    if (!item.menuKey) return item.visible !== false;
    if (!rbacLoaded) return false;
    return menuKeys.includes(item.menuKey);
  });

  const userMenuItems = [
    {
      label: `${user?.username}`,
      icon: 'pi pi-user',
      disabled: true,
    },
    { separator: true },
    {
      label: 'Profile',
      icon: 'pi pi-id-card',
      command: () => navigate('/profile'),
    },
    {
      label: 'Logout',
      icon: 'pi pi-sign-out',
      command: () => {
        dispatch(logout());
        navigate('/login');
      },
    },
  ];

  // Group items by section
  const sections = visibleItems.reduce<Record<string, NavItem[]>>((acc, item) => {
    const section = item.section || 'Other';
    if (!acc[section]) acc[section] = [];
    acc[section].push(item);
    return acc;
  }, {});

  // Get current page label for breadcrumb
  const currentPage = navItems.find((i) => i.path === location.pathname)?.label || '';

  const sidebarWidth = sidebarCollapsed ? '60px' : '220px';

  return (
    <div className="min-h-screen flex" style={{ background: 'var(--color-surface-ground)' }}>
      {/* ─── Sidebar ─── */}
      <aside
        className="em-sidebar flex-shrink-0 flex flex-column transition-all transition-duration-200"
        style={{ width: sidebarWidth, minHeight: '100vh', overflow: 'hidden' }}
        aria-label="Sidebar navigation"
      >
        {/* Logo area */}
        <div
          className="flex align-items-center justify-content-between px-3"
          style={{ height: '48px', borderBottom: '1px solid var(--color-surface-border)' }}
        >
          {!sidebarCollapsed && (
            <span className="font-bold text-lg" style={{ color: 'var(--color-primary)' }}>
              EMCURE
            </span>
          )}
          <Button
            icon={sidebarCollapsed ? 'pi pi-angle-right' : 'pi pi-angle-left'}
            rounded
            text
            severity="secondary"
            size="small"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            aria-label="Toggle sidebar"
            style={{ minWidth: '1.75rem', height: '1.75rem' }}
          />
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-2 px-1">
          {Object.entries(sections).map(([section, items]) => (
            <div key={section} className="mb-2">
              {!sidebarCollapsed && (
                <div
                  className="text-xs font-semibold uppercase mb-1 px-2"
                  style={{ color: 'var(--color-text-muted)', letterSpacing: '0.05em', fontSize: '0.6rem' }}
                >
                  {section}
                </div>
              )}
              {items.map((item) => {
                const isActive = location.pathname === item.path;
                return (
                  <button
                    key={item.path}
                    onClick={() => navigate(item.path)}
                    className={`w-full flex align-items-center gap-2 border-none cursor-pointer transition-colors transition-duration-200 ${sidebarCollapsed ? 'justify-content-center px-1 py-2' : 'px-2 py-2'} mb-1`}
                    style={{
                      background: isActive ? 'var(--color-primary-50)' : 'transparent',
                      borderRadius: 'var(--radius-md)',
                      borderLeft: !sidebarCollapsed ? (isActive ? '3px solid var(--color-primary)' : '3px solid transparent') : undefined,
                      color: isActive ? 'var(--color-primary)' : 'var(--color-text-primary)',
                      fontWeight: isActive ? 600 : 400,
                      fontSize: '12px',
                    }}
                    aria-label={item.label}
                    aria-current={isActive ? 'page' : undefined}
                    data-pr-tooltip={sidebarCollapsed ? item.label : undefined}
                    data-pr-position="right"
                  >
                    <i
                      className={item.icon}
                      style={{
                        fontSize: sidebarCollapsed ? '1.1rem' : '0.85rem',
                        color: isActive ? 'var(--color-primary)' : 'var(--color-text-secondary)',
                      }}
                    />
                    {!sidebarCollapsed && <span>{item.label}</span>}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
      </aside>

      {sidebarCollapsed && <Tooltip target="[data-pr-tooltip]" />}

      {/* ─── Main Content Area ─── */}
      <div className="flex-1 flex flex-column" style={{ minWidth: 0 }}>
        {/* Top Bar */}
        <header
          className="em-topbar flex align-items-center justify-content-between px-3"
          style={{ height: '48px' }}
          aria-label="Top bar"
        >
          {/* Left: Breadcrumb */}
          <div className="flex align-items-center gap-2">
            <span className="text-600" style={{ fontSize: '12px' }}>
              <i className="pi pi-home" style={{ fontSize: '11px' }} />
            </span>
            {currentPage && (
              <>
                <span className="text-400" style={{ fontSize: '11px' }}>/</span>
                <span className="font-medium" style={{ fontSize: '12px', color: 'var(--color-text-primary)' }}>
                  {currentPage}
                </span>
              </>
            )}
          </div>

          {/* Right: Notifications + User */}
          <div className="flex align-items-center gap-2">
            <Button
              icon="pi pi-bell"
              rounded
              text
              severity="secondary"
              aria-label="Notifications"
              className="p-overlay-badge"
              style={{ width: '2rem', height: '2rem' }}
            >
              <Badge value="3" severity="danger" style={{ fontSize: '0.6rem', minWidth: '1rem', height: '1rem', lineHeight: '1rem' }} />
            </Button>

            <Menu model={userMenuItems} popup ref={userMenu} />
            <Button
              rounded
              text
              onClick={(e) => userMenu.current?.toggle(e)}
              aria-label="User menu"
              className="flex align-items-center gap-1"
              style={{ padding: '0.25rem' }}
            >
              <Avatar
                label={user?.username?.charAt(0).toUpperCase() || 'U'}
                shape="circle"
                size="normal"
                style={{ background: 'var(--color-primary)', color: '#fff', width: '1.75rem', height: '1.75rem', fontSize: '0.75rem' }}
              />
              <span
                className="hidden lg:inline font-medium"
                style={{ color: 'var(--color-text-primary)', fontSize: '12px' }}
              >
                {user?.username}
              </span>
            </Button>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 p-3 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
