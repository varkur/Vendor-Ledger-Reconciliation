/**
 * Root Application component.
 * Wraps the app with all necessary providers.
 */

import { useEffect } from 'react';
import { Provider } from 'react-redux';
import { PrimeReactProvider } from 'primereact/api';
import { store, useAppDispatch } from '@app/store';
import { AppRouter } from '@app/router/AppRouter';
import { QueryProvider } from '@app/providers/QueryProvider';
import { restoreSession } from '@features/authentication/store/authSlice';

/**
 * Restores the auth session from stored tokens on startup, so a page refresh
 * doesn't log the user out.
 */
const AuthBootstrap = ({ children }: { children: React.ReactNode }) => {
  const dispatch = useAppDispatch();
  useEffect(() => {
    dispatch(restoreSession());
  }, [dispatch]);
  return <>{children}</>;
};

export const App = () => {
  return (
    <Provider store={store}>
      <QueryProvider>
        <PrimeReactProvider>
          <AuthBootstrap>
            <AppRouter />
          </AuthBootstrap>
        </PrimeReactProvider>
      </QueryProvider>
    </Provider>
  );
};
