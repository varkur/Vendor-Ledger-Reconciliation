frontend/
├── ci/                          # CI pipeline configs
├── docker/                      # Dockerfile and container configs
├── public/
│   └── config.json              # Runtime environment config (Req 15)
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/                     # Playwright E2E tests
└── src/
    ├── app/                     # Application bootstrap (Req 1)
    │   ├── config/              # App-level configuration
    │   ├── providers/           # React context providers
    │   ├── routes/              # Root route definitions
    │   └── store/               # Redux store setup
    ├── features/                # Domain feature modules (Req 3)
    │   ├── authentication/      # Auth flows, login, SSO
    │   ├── user-management/     # User CRUD, profiles
    │   ├── dashboard/           # Main dashboard
    │   ├── reports/             # Reporting & analytics
    │   ├── notifications/       # Notification center
    │   └── audit/               # Audit log viewing
    │       ├── api/             # Infrastructure layer (Req 2)
    │       ├── components/      # Presentation layer
    │       ├── hooks/           # Application layer
    │       ├── models/          # Domain layer
    │       ├── pages/           # Presentation layer (routes)
    │       ├── routes/          # Route config export
    │       ├── store/           # Application layer (Redux slice)
    │       └── index.ts         # Barrel export (public API)
    ├── shared/                  # Cross-feature library (Req 4)
    │   ├── components/
    │   ├── hooks/
    │   ├── services/
    │   ├── utils/
    │   ├── constants/
    │   ├── types/
    │   ├── styles/
    │   └── index.ts
    ├── core/                    # Singleton services (Req 6-12)
    │   ├── api/                 # Axios client, interceptors
    │   ├── auth/                # JWT/OAuth2 management
    │   ├── rbac/                # Permission engine
    │   ├── logging/             # Structured logger
    │   ├── telemetry/           # OpenTelemetry collector
    │   ├── error-handling/      # Error boundaries
    │   ├── security/            # CSP, XSS, sanitization
    │   └── index.ts
    ├── assets/                  # Static resources
    │   ├── images/
    │   ├── fonts/
    │   └── icons/
    └── i18n/                    # Internationalization
        └── locales/
