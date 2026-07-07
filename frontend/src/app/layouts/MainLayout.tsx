/**
 * Main application layout — Sakai-style with Emcure Red branding.
 * Dark sidebar, top header with company selector, Firmway-equivalent navigation.
 */

import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAppSelector } from '@app/store';

interface NavItem {
  label: string;
  icon: string;
  path: string;
  hasSubmenu?: boolean;
}

const navItems: NavItem[] = [
  { label: 'Manage Party', icon: 'pi pi-users', path: '/manage-party' },
  { label: 'Request Statement', icon: 'pi pi-file-edit', path: '/request-statement' },
  { label: 'Direct Reconciliation', icon: 'pi pi-check-circle', path: '/direct-reconciliation' },
  { label: 'Track Reconciliation', icon: 'pi pi-chart-line', path: '/track-reconciliation' },
  { label: 'Reports', icon: 'pi pi-chart-bar', path: '/reports' },
  { label: 'Automation', icon: 'pi pi-cog', path: '/automation', hasSubmenu: true },
  { label: 'Access Management', icon: 'pi pi-lock', path: '/access-management', hasSubmenu: true },
  { label: 'Settings', icon: 'pi pi-sliders-h', path: '/settings', hasSubmenu: true },
  { label: 'ERP Integration', icon: 'pi pi-link', path: '/erp-integration', hasSubmenu: true },
];

export const MainLayout = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAppSelector((state) => state.auth);
  const [expandedMenus, setExpandedMenus] = useState<string[]>([]);

  const isActive = (path: string) => location.pathname.startsWith(path);

  const toggleSubmenu = (path: string) => {
    setExpandedMenus((prev) =>
      prev.includes(path) ? prev.filter((p) => p !== path) : [...prev, path]
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
            <button
              key={item.path}
              className={`em-nav-item ${isActive(item.path) ? 'active' : ''}`}
              onClick={() => {
                if (item.hasSubmenu) {
                  toggleSubmenu(item.path);
                } else {
                  navigate(item.path);
                }
              }}
              aria-label={item.label}
              aria-current={isActive(item.path) ? 'page' : undefined}
            >
              <i className={item.icon} />
              <span style={{ flex: 1 }}>{item.label}</span>
              {item.hasSubmenu && (
                <i
                  className={`pi ${expandedMenus.includes(item.path) ? 'pi-chevron-down' : 'pi-chevron-right'}`}
                  style={{ fontSize: 10 }}
                />
              )}
            </button>
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
