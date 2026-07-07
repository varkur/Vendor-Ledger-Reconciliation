/**
 * Root Application component.
 * Wraps the app with all necessary providers.
 */

import { Provider } from 'react-redux';
import { PrimeReactProvider } from 'primereact/api';
import { store } from '@app/store';
import { AppRouter } from '@app/router/AppRouter';
import { QueryProvider } from '@app/providers/QueryProvider';

export const App = () => {
  return (
    <Provider store={store}>
      <QueryProvider>
        <PrimeReactProvider>
          <AppRouter />
        </PrimeReactProvider>
      </QueryProvider>
    </Provider>
  );
};
