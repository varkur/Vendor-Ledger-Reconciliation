/**
 * Microsoft OAuth2 Callback Page.
 * Handles the redirect back from Azure AD after user authenticates.
 * Exchanges the authorization code for app tokens and navigates to dashboard.
 */

import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Button } from 'primereact/button';
import { useAppDispatch } from '@app/store';
import { fetchCurrentUser } from '../store/authSlice';
import { microsoftApi } from '../api/microsoftApi';
import { storageService } from '@shared/services/storageService';

export const MicrosoftCallbackPage = () => {
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get('code');
    const errorParam = searchParams.get('error_description') || searchParams.get('error');

    if (errorParam) {
      setError(errorParam);
      return;
    }

    if (!code) {
      setError('No authorization code received from Microsoft.');
      return;
    }

    // Exchange code for app tokens
    microsoftApi
      .exchangeCode(code)
      .then(async (tokenRes) => {
        // Store tokens in memory
        storageService.setAccessToken(tokenRes.access_token);
        storageService.setRefreshToken(tokenRes.refresh_token);

        // Fetch user profile
        await dispatch(fetchCurrentUser());

        // Navigate to dashboard
        const redirect = sessionStorage.getItem('redirectAfterLogin') || '/dashboard';
        sessionStorage.removeItem('redirectAfterLogin');
        navigate(redirect, { replace: true });
      })
      .catch((err: any) => {
        const detail = err.response?.data?.detail || err.message || 'Microsoft login failed';
        setError(detail);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) {
    return (
      <div
        className="flex align-items-center justify-content-center min-h-screen"
        style={{ background: 'var(--color-surface-ground)' }}
      >
        <div className="em-login-card p-6 text-center" style={{ maxWidth: '420px' }}>
          <i
            className="pi pi-times-circle mb-3"
            style={{ fontSize: '3rem', color: 'var(--color-error)' }}
          />
          <h2 className="text-xl font-bold mb-2" style={{ color: 'var(--color-text-primary)' }}>
            Login Failed
          </h2>
          <p className="mb-4" style={{ color: 'var(--color-text-secondary)', fontSize: '14px' }}>
            {error}
          </p>
          <Button
            label="Back to Login"
            icon="pi pi-arrow-left"
            onClick={() => navigate('/login')}
          />
        </div>
      </div>
    );
  }

  return (
    <div
      className="flex align-items-center justify-content-center min-h-screen"
      style={{ background: 'var(--color-surface-ground)' }}
    >
      <div className="em-login-card p-6 text-center" style={{ maxWidth: '420px' }}>
        <ProgressSpinner
          style={{ width: '50px', height: '50px' }}
          strokeWidth="4"
          aria-label="Signing in with Microsoft"
        />
        <p className="mt-3" style={{ color: 'var(--color-text-secondary)' }}>
          Signing in with Microsoft…
        </p>
      </div>
    </div>
  );
};
