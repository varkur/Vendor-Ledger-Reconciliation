"""
Application settings using Pydantic BaseSettings.
Loads configuration from environment variables and .env files.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Enterprise application configuration."""

    # Application
    APP_NAME: str = Field(default="Enterprise FastAPI", description="Application name")
    APP_VERSION: str = Field(default="1.0.0", description="Application version")
    DEBUG: bool = Field(default=False, description="Debug mode")

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/enterprise_db",
        description="Async database connection string",
    )
    DB_POOL_SIZE: int = Field(default=20, description="Database connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=10, description="Max overflow connections")

    # JWT Authentication
    JWT_SECRET_KEY: str = Field(
        default="change-me-in-production-use-strong-secret",
        description="JWT signing secret key",
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30, description="Access token expiry in minutes"
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=7, description="Refresh token expiry in days"
    )

    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_FILE_PATH: str = Field(
        default="logs/application.log", description="Log file path"
    )
    LOG_MAX_BYTES: int = Field(
        default=10 * 1024 * 1024, description="Max log file size (10MB)"
    )
    LOG_BACKUP_COUNT: int = Field(default=10, description="Number of log backups")

    # Redis (Optional Cache)
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0", description="Redis connection URL"
    )

    # Celery
    CELERY_BROKER_URL: str = Field(
        default="redis://localhost:6379/1", description="Celery broker URL"
    )
    CELERY_RESULT_BACKEND: str = Field(
        default="", description="Celery result backend URL"
    )

    # OpenTelemetry
    OTEL_EXPORTER_ENDPOINT: str = Field(
        default="http://localhost:4317", description="OpenTelemetry exporter endpoint"
    )
    OTEL_SERVICE_NAME: str = Field(
        default="enterprise-api", description="OpenTelemetry service name"
    )

    # Azure AD / Microsoft SSO
    AZURE_CLIENT_ID: str = Field(default="", description="Azure App Registration client ID")
    AZURE_CLIENT_SECRET: str = Field(default="", description="Azure App Registration client secret")
    AZURE_TENANT_ID: str = Field(default="", description="Azure AD tenant ID")
    AZURE_REDIRECT_URI: str = Field(
        default="http://localhost:3000/auth/microsoft/callback",
        description="OAuth2 redirect URI (must match Azure App Registration)",
    )

    # Employee AD (Darwin) Service
    EMPLOYEE_AD_BASE_URL: str = Field(
        default="https://ad-prod-darwinsvc-prod.apps.emart.oneemcure.local/adintegratorservices/rest/v1",
        description="Base URL for the Darwin AD integrator service",
    )

    # Encryption (for SAP credentials and other sensitive settings)
    ENCRYPTION_KEY: str = Field(
        default="",
        description="Fernet symmetric encryption key for sensitive data (base64-encoded 32 bytes)",
    )

    # CORS
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000"], description="Allowed CORS origins"
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


# Singleton settings instance
settings = Settings()
