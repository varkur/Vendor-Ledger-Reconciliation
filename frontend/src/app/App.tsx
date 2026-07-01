/**
 * Root Application component.
 * Wraps the app with all necessary providers.
 */

import { Provider } from 'react-redux';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PrimeReactProvider } from 'primereact/api';
import { store } from '@app/store';
import { AppRouter } from '@app/router/AppRouter';

// TanStack Query client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export const App = () => {
  return (
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>
        <PrimeReactProvider>
          <AppRouter />
        </PrimeReactProvider>
      </QueryClientProvider>
    </Provider>
  );
};
