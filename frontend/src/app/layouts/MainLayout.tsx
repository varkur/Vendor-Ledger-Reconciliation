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

import { useState, useEffect, useRef } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAppSelector, useAppDispatch } from '@app/store';
import { fetchEntities, selectEntity, type CompanyEntity } from '@app/store/entitySlice';
import { useQueryClient } from '@tanstack/react-query';

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
  const [expandedMenus, setExpandedMenus] = useState<string[]>(['Account Reco']);
  const [entityDropdownOpen, setEntityDropdownOpen] = useState(false);
  const entityDropdownRef = useRef<HTMLDivElement>(null);

  // Load entities on mount
  useEffect(() => {
    dispatch(fetchEntities());
  }, [dispatch]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (entityDropdownRef.current && !entityDropdownRef.current.contains(event.target as Node)) {
        setEntityDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleEntityChange = (entity: CompanyEntity) => {
    dispatch(selectEntity(entity));
    setEntityDropdownOpen(false);
    // Invalidate all queries so data refetches for the new entity
    queryClient.invalidateQueries();
  };

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
            <div className="em-company-selector" ref={entityDropdownRef} style={{ position: 'relative' }}>
              <button
                onClick={() => setEntityDropdownOpen(!entityDropdownOpen)}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '6px 10px',
                  borderRadius: 4,
                  fontSize: 14,
                  color: 'inherit',
                }}
                aria-haspopup="listbox"
                aria-expanded={entityDropdownOpen}
              >
                <span>{selectedEntity?.name || 'Select Entity'}</span>
                <i className={`pi ${entityDropdownOpen ? 'pi-chevron-up' : 'pi-chevron-down'}`} style={{ fontSize: 10 }} />
              </button>
              {entityDropdownOpen && entities.length > 0 && (
                <div
                  style={{
                    position: 'absolute',
                    top: '100%',
                    left: 0,
                    minWidth: 280,
                    background: '#fff',
                    border: '1px solid var(--color-border)',
                    borderRadius: 6,
                    boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
                    zIndex: 1000,
                    marginTop: 4,
                  }}
                  role="listbox"
                  aria-label="Select company entity"
                >
                  {entities.map((entity) => (
                    <button
                      key={entity.id}
                      role="option"
                      aria-selected={entity.id === selectedEntity?.id}
                      onClick={() => handleEntityChange(entity)}
                      style={{
                        display: 'block',
                        width: '100%',
                        textAlign: 'left',
                        padding: '10px 16px',
                        border: 'none',
                        background: entity.id === selectedEntity?.id ? 'var(--color-primary-50, #f0f0f0)' : 'transparent',
                        cursor: 'pointer',
                        fontSize: 14,
                        fontWeight: entity.id === selectedEntity?.id ? 600 : 400,
                      }}
                    >
                      {entity.name}
                    </button>
                  ))}
                </div>
              )}
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
