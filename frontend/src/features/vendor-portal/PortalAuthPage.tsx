/**
 * Vendor Portal Authentication — Reads token from URL and validates via backend API.
 * Vendors access this via a unique link sent in their email.
 *
 * Connects to: POST /api/v1/vlr/portal/validate-token
 * Requirements: 24.1, 33.1, 33.2
 */

import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Button } from 'primereact/button';
import { Message } from 'primereact/message';

import { useValidateToken } from './hooks/usePortal';
import { usePortalContext } from './context/PortalContext';

type AuthStatus = 'authenticating' | 'success' | 'expired' | 'invalid' | 'error';

export const PortalAuthPage = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<AuthStatus>('authenticating');
  const [errorMessage, setErrorMessage] = useState('');

  const { setAuthenticated } = usePortalContext();
  const validateMutation = useValidateToken();

  useEffect(() => {
    const token = searchParams.get('token');

    if (!token) {
      setStatus('invalid');
      return;
    }

    validateMutation.mutate(token, {
      onSuccess: (data) => {
        setAuthenticated(token, data);
        setStatus('success');
        // Auto-redirect after successful auth
        setTimeout(() => navigate('/portal/upload'), 1500);
      },
      onError: (error) => {
        const statusCode = error.response?.status;
        const detail =
          error.response?.data?.detail || 'An unexpected error occurred.';

        if (statusCode === 410) {
          setStatus('expired');
          setErrorMessage(detail);
        } else if (statusCode === 404) {
          setStatus('invalid');
          setErrorMessage(detail);
        } else {
          setStatus('error');
          setErrorMessage(detail);
        }
      },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const handleRetry = () => {
    const token = searchParams.get('token');
    if (!token) return;

    setStatus('authenticating');
    setErrorMessage('');
    validateMutation.mutate(token, {
      onSuccess: (data) => {
        setAuthenticated(token, data);
        setStatus('success');
        setTimeout(() => navigate('/portal/upload'), 1500);
      },
      onError: (error) => {
        const statusCode = error.response?.status;
        const detail =
          error.response?.data?.detail || 'An unexpected error occurred.';

        if (statusCode === 410) {
          setStatus('expired');
          setErrorMessage(detail);
        } else if (statusCode === 404) {
          setStatus('invalid');
          setErrorMessage(detail);
        } else {
          setStatus('error');
          setErrorMessage(detail);
        }
      },
    });
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#f4f6f9',
      }}
    >
      <div className="em-card" style={{ width: 450, textAlign: 'center', padding: 40 }}>
        <div style={{ marginBottom: 24 }}>
          <h2 style={{ margin: 0, color: 'var(--color-primary, #2563eb)' }}>
            Vendor Ledger Reconciliation
          </h2>
          <p style={{ color: 'var(--color-text-muted)', margin: '8px 0 0' }}>
            Vendor Portal
          </p>
        </div>

        {status === 'authenticating' && (
          <div>
            <ProgressSpinner style={{ width: 50, height: 50 }} />
            <p style={{ marginTop: 16 }}>Verifying your access token...</p>
          </div>
        )}

        {status === 'success' && validateMutation.data && (
          <div>
            <i
              className="pi pi-check-circle"
              style={{ fontSize: '3rem', color: 'var(--color-success, #22c55e)' }}
            />
            <h3 style={{ marginTop: 16 }}>
              Welcome, {validateMutation.data.vendor_name}
            </h3>
            <p style={{ color: 'var(--color-text-muted)' }}>
              Authentication successful. Redirecting to portal...
            </p>
            <ProgressSpinner style={{ width: 30, height: 30 }} />
          </div>
        )}

        {status === 'expired' && (
          <div>
            <i
              className="pi pi-clock"
              style={{ fontSize: '3rem', color: 'var(--color-warning, #f59e0b)' }}
            />
            <h3 style={{ marginTop: 16 }}>Link Expired</h3>
            <p style={{ color: 'var(--color-text-muted)' }}>
              {errorMessage ||
                'This access link has expired. Please contact your reconciliation coordinator to request a new link.'}
            </p>
            <Button
              label="Request New Link"
              icon="pi pi-envelope"
              className="mt-3"
            />
          </div>
        )}

        {status === 'invalid' && (
          <div>
            <i
              className="pi pi-times-circle"
              style={{ fontSize: '3rem', color: 'var(--color-error, #ef4444)' }}
            />
            <h3 style={{ marginTop: 16 }}>Invalid Access</h3>
            <p style={{ color: 'var(--color-text-muted)' }}>
              {errorMessage ||
                'The link is invalid or missing required authentication parameters. Please use the link provided in your email.'}
            </p>
          </div>
        )}

        {status === 'error' && (
          <div>
            <i
              className="pi pi-exclamation-triangle"
              style={{ fontSize: '3rem', color: 'var(--color-error, #ef4444)' }}
            />
            <h3 style={{ marginTop: 16 }}>Connection Error</h3>
            <Message
              severity="error"
              text={errorMessage || 'Unable to verify your access token. Please try again.'}
              className="mb-3 w-full"
            />
            <Button
              label="Retry"
              icon="pi pi-refresh"
              onClick={handleRetry}
              className="mt-2"
            />
          </div>
        )}
      </div>
    </div>
  );
};
