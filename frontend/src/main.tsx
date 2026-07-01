import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from '@app/App';

// PrimeReact CSS
import 'primereact/resources/themes/lara-light-blue/theme.css';
import 'primereact/resources/primereact.min.css';
import 'primeicons/primeicons.css';
import 'primeflex/primeflex.css';

// Emcure theme overrides (must come after PrimeReact CSS)
import '@assets/styles/theme-overrides.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
