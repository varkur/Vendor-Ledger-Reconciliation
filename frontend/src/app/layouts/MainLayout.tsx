/**
 * Main application layout — Sakai-style with Emcure Red branding.
 * Dark sidebar with nested navigation matching Firmway's structure:
 * - Dashboard
 * - Confirmation (submenu)
 * - Account Reco (submenu with Manage Party, Request Statement, etc.)
 * - Data Management
 * - Settings (submenu with sub-pages)
 * - Utilities
 */

import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAppSelector } from '@app/store';

interface SubNavItem {
  label: string;
  icon?: string;
  path: string;
}

interface NavItem {
  label: string;
  icon: string;
  path?: string;
  children?: SubNavItem[];
}

const navItems: NavItem[] = [
  {
    label: 'Dashboard',
    icon: 'pi pi-home',
    path: '/dashboard',
  },
  {
    label: 'Confirmation',
    icon: 'pi pi-check-square',
    children: [
      { label: 'Pending Confirmations', path: '/track-reconciliation' },
      { label: 'Exceptions', path: '/exceptions' },
    ],
  },
  {
    label: 'Account Reco',
    icon: 'pi pi-sync',
    children: [
      { label: 'Manage Party', path: '/manage-party' },
      { label: 'Request Statement', path: '/request-statement' },
      { label: 'Direct Reconciliation', path: '/direct-reconciliation' },
      { label: 'Track Reconciliation', path: '/track-reconciliation' },
      { label: 'Reports', path: '/reports' },
      { label: 'Notifications', path: '/notifications' },
    ],
  },
  {
    label: 'Data Management',
    icon: 'pi pi-database',
    children: [
      { label: 'Recovery & Follow-up', path: '/recovery' },
    ],
  },
  {
    label: 'Settings',
    icon: 'pi pi-cog',
    children: [
      { label: 'Manage Users', path: '/access-management/roles' },
      { label: 'Company Profile', path: '/settings' },
      { label: 'Email Attachments', path: '/settings' },
      { label: 'Document Types', path: '/settings' },
      { label: 'Reminders', path: '/settings' },
      { label: 'Email Config', path: '/settings' },
      { label: 'Domain Config', path: '/settings' },
      { label: 'Notification', path: '/settings' },
      { label: 'Global Settings', path: '/settings' },
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
  const { user } = useAppSelector((state) => state.auth);
  const [expandedMenus, setExpandedMenus] = useState<string[]>(['Account Reco']);

  const isActive = (path: string) => location.pathname === path || location.pathname.startsWith(path + '/');

  const isParentActive = (item: NavItem) => {
    if (item.path) return isActive(item.path);
    return item.children?.some((child) => isActive(child.path)) ?? false;
  };

  const toggleSubmenu = (label: string) => {
    setExpandedMenus((prev) =>
      prev.includes(label) ? prev.filter((l) => l !== label) : [...prev, label]
    );
  };

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

        {/* Navigation */}
        <nav className="em-sidebar-nav">
          {navItems.map((item) => (
            <div key={item.label}>
              {/* Parent item */}
              <button
                className={`em-nav-item ${isParentActive(item) ? 'active' : ''}`}
                onClick={() => {
                  if (item.children) {
                    toggleSubmenu(item.label);
                  } else if (item.path) {
                    navigate(item.path);
                  }
                }}
                aria-label={item.label}
                aria-expanded={item.children ? expandedMenus.includes(item.label) : undefined}
              >
                <i className={item.icon} />
                <span style={{ flex: 1 }}>{item.label}</span>
                {item.children && (
                  <i
                    className={`pi ${expandedMenus.includes(item.label) ? 'pi-chevron-down' : 'pi-chevron-right'}`}
                    style={{ fontSize: 10 }}
                  />
                )}
              </button>

              {/* Children submenu */}
              {item.children && expandedMenus.includes(item.label) && (
                <div className="em-submenu">
                  {item.children.map((child) => (
                    <button
                      key={child.path + child.label}
                      className={`em-nav-subitem ${isActive(child.path) ? 'active' : ''}`}
                      onClick={() => navigate(child.path)}
                      aria-label={child.label}
                      aria-current={isActive(child.path) ? 'page' : undefined}
                    >
                      {child.icon && <i className={child.icon} />}
                      <span>{child.label}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </nav>
      </aside>

      {/* ─── Main Content ─── */}
      <div className="flex-1 flex flex-column" style={{ minWidth: 0 }}>
        {/* Top Bar */}
        <header className="em-topbar" aria-label="Top bar">
          <div className="em-topbar-left">
            <i className="pi pi-question-circle" style={{ fontSize: 18, color: 'var(--color-text-muted)' }} />
            <div className="em-company-selector">
              <span>Emcure Pharmaceuticals Limited</span>
              <i className="pi pi-chevron-down" style={{ fontSize: 10 }} />
            </div>
          </div>

          <div className="em-topbar-right">
            <span className="em-user-info">
              {user?.username || 'User'}
            </span>
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: '50%',
                background: 'var(--color-primary-50)',
                border: '1px solid var(--color-primary-100)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
              }}
            >
              <i className="pi pi-user" style={{ fontSize: 14, color: 'var(--color-primary)' }} />
            </div>
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
