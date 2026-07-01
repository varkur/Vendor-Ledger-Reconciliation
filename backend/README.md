# Enterprise FastAPI Backend
backend/
├── .env.example
├── .github/workflows/
│   ├── ci.yml                              # CI: lint, test, build, security scan
│   └── cd.yml                              # CD: deploy to staging/prod
├── alembic.ini                             # Alembic config
├── Makefile                                # Dev commands
├── pyproject.toml                          # Project metadata & tool config
├── README.md
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
│
├── src/
│   ├── main.py                             # FastAPI app entry point
│   │
│   ├── api/                                # ── API LAYER ──
│   │   ├── v1/
│   │   │   ├── endpoints/                  # Controllers
│   │   │   │   ├── auth_controller.py
│   │   │   │   ├── health_controller.py
│   │   │   │   ├── order_controller.py
│   │   │   │   └── user_controller.py
│   │   │   ├── schemas/                    # Request/Response Pydantic models
│   │   │   │   ├── auth_schema.py
│   │   │   │   ├── common_schema.py
│   │   │   │   ├── order_request.py
│   │   │   │   ├── order_response.py
│   │   │   │   ├── user_request.py
│   │   │   │   └── user_response.py
│   │   │   ├── dependencies.py             # FastAPI DI for v1
│   │   │   └── router.py                   # v1 route aggregation
│   │   ├── v2/                             # Future API version
│   │   │   ├── endpoints/
│   │   │   ├── schemas/
│   │   │   └── router.py
│   │   └── middleware/
│   │       ├── auth_middleware.py
│   │       ├── correlation_id.py
│   │       ├── exception_handler.py
│   │       ├── rate_limiter.py
│   │       └── request_logging.py
│   │
│   ├── application/                        # ── APPLICATION LAYER ──
│   │   ├── use_cases/
│   │   │   ├── user/   (create, get, update, delete)
│   │   │   ├── order/  (create_order)
│   │   │   └── auth/   (login, refresh_token)
│   │   ├── services/                       # Application services
│   │   │   ├── user_service.py
│   │   │   ├── order_service.py
│   │   │   └── notification_service.py
│   │   ├── commands/                       # CQRS commands
│   │   ├── queries/                        # CQRS queries
│   │   ├── dto/                            # Data transfer objects
│   │   ├── validators/                     # Business rule validators
│   │   ├── event_handlers/                 # React to domain events
│   │   └── exceptions/
│   │
│   ├── domain/                             # ── DOMAIN LAYER (pure, no deps) ──
│   │   ├── entities/       (base_entity, user, role, order)
│   │   ├── aggregates/     (user_aggregate, order_aggregate)
│   │   ├── value_objects/   (email, address, money)
│   │   ├── repositories/   (base, user, order – interfaces only)
│   │   ├── services/        (user_domain_service, order_domain_service)
│   │   ├── events/          (base_event, user_events, order_events)
│   │   ├── specifications/  (base_specification, user_specification)
│   │   ├── enums/           (user_status, order_status)
│   │   └── exceptions/      (domain_exceptions)
│   │
│   ├── infrastructure/                     # ── INFRASTRUCTURE LAYER ──
│   │   ├── database/
│   │   │   ├── models/          (base_model, user_model, order_model)
│   │   │   ├── repositories/   (base_impl, user_impl, order_impl)
│   │   │   ├── migrations/versions/
│   │   │   ├── session.py       # Async session factory
│   │   │   └── unit_of_work.py  # Transaction management
│   │   ├── security/
│   │   │   ├── jwt_provider.py
│   │   │   ├── password_encoder.py
│   │   │   ├── auth_manager.py
│   │   │   ├── oauth2_provider.py
│   │   │   └── rbac_manager.py
│   │   ├── external/
│   │   │   ├── email/      (smtp_provider)
│   │   │   ├── storage/    (s3_provider)
│   │   │   ├── payment/    (stripe_provider)
│   │   │   ├── sms/        (sms_provider)
│   │   │   └── third_party/
│   │   ├── cache/           (redis_cache)
│   │   └── background/
│   │       ├── celery_app.py
│   │       ├── tasks/       (user_tasks, order_tasks)
│   │       └── schedulers/  (periodic_tasks)
│   │
│   ├── common/                             # ── SHARED/COMMON ──
│   │   ├── constants/
│   │   ├── utilities/       (date_utils)
│   │   ├── helpers/
│   │   ├── validators/
│   │   ├── decorators/
│   │   ├── base_classes/    (base_service)
│   │   └── responses/       (api_response)
│   │
│   ├── config/                             # ── CONFIGURATION ──
│   │   ├── settings.py
│   │   ├── database.py
│   │   ├── logging_config.py
│   │   ├── dependency_injection.py
│   │   └── feature_flags.py
│   │
│   └── observability/                      # ── OBSERVABILITY ──
│       ├── structured_logger.py
│       ├── correlation.py
│       ├── tracing.py
│       ├── metrics.py
│       └── health_checks.py
│
├── tests/
│   ├── conftest.py
│   ├── unit/        (domain/, application/, infrastructure/)
│   ├── integration/ (api/, database/)
│   ├── contract/
│   ├── e2e/
│   ├── performance/
│   └── fixtures/
│
├── scripts/
│   ├── seed_data.py
│   ├── db_migration.py
│   └── generate_openapi.py
│
├── docs/
│   ├── architecture/  (ARCHITECTURE.md)
│   ├── api/           (openapi.yaml)
│   ├── adr/           (Architecture Decision Records)
│   └── diagrams/
│
└── deployment/
    ├── docker/
    │   ├── Dockerfile
    │   ├── Dockerfile.dev
    │   ├── docker-compose.yml
    │   └── docker-compose.test.yml
    ├── kubernetes/
    │   ├── base/   (deployment, service, configmap, hpa)
    │   └── overlays/ (dev, staging, production)
    └── helm/
        ├── Chart.yaml
        ├── values.yaml
        ├── values-staging.yaml
        ├── values-production.yaml
        └── templates/
