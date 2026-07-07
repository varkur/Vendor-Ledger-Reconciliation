/**
 * Vendor Portal Authentication — Reads token from URL and authenticates the vendor.
 * Vendors access this via a unique link sent in their email.
 */

import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Button } from 'primereact/button';

type AuthStatus = 'authenticating' | 'success' | 'expired' | 'invalid';

export const PortalAuthPage = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<AuthStatus>('authenticating');
  const [vendorName, setVendorName] = useState('');

  useEffect(() => {
    const token = searchParams.get('token');

    if (!token) {
      setStatus('invalid');
      return;
    }

    // Simulate token validation
    const timer = setTimeout(() => {
      // Mock: tokens starting with 'exp' are expired, 'inv' are invalid, else success
      if (token.startsWith('exp')) {
        setStatus('expired');
      } else if (token.startsWith('inv')) {
        setStatus('invalid');
      } else {
        setStatus('success');
        setVendorName('A S C PHARMASPECIALITIES LLP');
        // Auto-redirect after successful auth
        setTimeout(() => navigate('/portal/upload'), 1500);
      }
    }, 2000);

    return () => clearTimeout(timer);
  }, [searchParams, navigate]);

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f4f6f9' }}>
      <div className="em-card" style={{ width: 450, textAlign: 'center', padding: 40 }}>
        <div style={{ marginBottom: 24 }}>
          <h2 style={{ margin: 0, color: 'var(--color-primary, #2563eb)' }}>Vendor Ledger Reconciliation</h2>
          <p style={{ color: 'var(--color-text-muted)', margin: '8px 0 0' }}>Vendor Portal</p>
        </div>

        {status === 'authenticating' && (
          <div>
            <ProgressSpinner style={{ width: 50, height: 50 }} />
            <p style={{ marginTop: 16 }}>Verifying your access token...</p>
          </div>
        )}

        {status === 'success' && (
          <div>
            <i className="pi pi-check-circle" style={{ fontSize: '3rem', color: 'var(--color-success, #22c55e)' }} />
            <h3 style={{ marginTop: 16 }}>Welcome, {vendorName}</h3>
            <p style={{ color: 'var(--color-text-muted)' }}>Authentication successful. Redirecting to portal...</p>
            <ProgressSpinner style={{ width: 30, height: 30 }} />
          </div>
        )}

        {status === 'expired' && (
          <div>
            <i className="pi pi-clock" style={{ fontSize: '3rem', color: 'var(--color-warning, #f59e0b)' }} />
            <h3 style={{ marginTop: 16 }}>Link Expired</h3>
            <p style={{ color: 'var(--color-text-muted)' }}>
              This access link has expired. Please contact your reconciliation coordinator to request a new link.
            </p>
            <Button label="Request New Link" icon="pi pi-envelope" className="mt-3" />
          </div>
        )}

        {status === 'invalid' && (
          <div>
            <i className="pi pi-times-circle" style={{ fontSize: '3rem', color: 'var(--color-error, #ef4444)' }} />
            <h3 style={{ marginTop: 16 }}>Invalid Access</h3>
            <p style={{ color: 'var(--color-text-muted)' }}>
              The link is invalid or missing required authentication parameters. Please use the link provided in your email.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
