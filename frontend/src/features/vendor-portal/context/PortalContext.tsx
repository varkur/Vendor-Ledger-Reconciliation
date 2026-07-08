/**
 * Portal context for sharing authenticated state across vendor portal pages.
 *
 * After successful token validation on the auth page, the token and case info
 * are stored in this context so that upload, statement, and sign-off pages
 * can access them without re-authenticating.
 *
 * Requirements: 24.1, 24.2, 24.3, 24.4
 */

import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';
import type { ValidateTokenResponse } from '../api/portalApi';

interface PortalContextValue {
  /** The portal access token from the URL. */
  portalToken: string | null;
  /** Case info returned from validate-token. */
  caseInfo: ValidateTokenResponse | null;
  /** Store token and case info after successful validation. */
  setAuthenticated: (token: string, info: ValidateTokenResponse) => void;
  /** Clear portal auth state. */
  clearAuth: () => void;
  /** Whether the portal session is authenticated. */
  isAuthenticated: boolean;
}

const PortalContext = createContext<PortalContextValue | undefined>(undefined);

const PORTAL_TOKEN_KEY = 'vlr_portal_token';
const PORTAL_CASE_KEY = 'vlr_portal_case';

export function PortalProvider({ children }: { children: ReactNode }) {
  const [portalToken, setPortalToken] = useState<string | null>(() => {
    return sessionStorage.getItem(PORTAL_TOKEN_KEY);
  });

  const [caseInfo, setCaseInfo] = useState<ValidateTokenResponse | null>(() => {
    const stored = sessionStorage.getItem(PORTAL_CASE_KEY);
    return stored ? JSON.parse(stored) : null;
  });

  const setAuthenticated = useCallback(
    (token: string, info: ValidateTokenResponse) => {
      setPortalToken(token);
      setCaseInfo(info);
      sessionStorage.setItem(PORTAL_TOKEN_KEY, token);
      sessionStorage.setItem(PORTAL_CASE_KEY, JSON.stringify(info));
    },
    []
  );

  const clearAuth = useCallback(() => {
    setPortalToken(null);
    setCaseInfo(null);
    sessionStorage.removeItem(PORTAL_TOKEN_KEY);
    sessionStorage.removeItem(PORTAL_CASE_KEY);
  }, []);

  return (
    <PortalContext.Provider
      value={{
        portalToken,
        caseInfo,
        setAuthenticated,
        clearAuth,
        isAuthenticated: !!portalToken && !!caseInfo,
      }}
    >
      {children}
    </PortalContext.Provider>
  );
}

/**
 * Hook to access portal authentication context.
 * Must be used within a PortalProvider.
 */
export function usePortalContext() {
  const context = useContext(PortalContext);
  if (context === undefined) {
    throw new Error('usePortalContext must be used within a PortalProvider');
  }
  return context;
}
