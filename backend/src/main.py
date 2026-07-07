"""
FastAPI application entry point.
Configures middleware, routers, CORS, and OpenAPI documentation.
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from src.api.middleware.audit_context_middleware import AuditContextMiddleware
from src.api.middleware.correlation_id import CorrelationIdMiddleware
from src.api.middleware.exception_handler import ExceptionHandlerMiddleware
from src.api.middleware.rate_limiter import RateLimitMiddleware
from src.api.middleware.request_logging import RequestLoggingMiddleware
from src.api.v1.router import api_v1_router
from src.config.logging_config import configure_file_logging
from src.config.settings import settings
from src.observability.structured_logger import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    # Startup
    configure_logging()
    configure_file_logging()
    yield
    # Shutdown (cleanup resources here)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Enterprise-grade FastAPI application with Clean Architecture",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── OpenAPI Security Scheme (enables Swagger Authorize button) ───
from fastapi.openapi.utils import get_openapi


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    # Ensure the HTTPBearer scheme is defined (matches FastAPI's HTTPBearer dependency)
    if "components" not in openapi_schema:
        openapi_schema["components"] = {}
    if "securitySchemes" not in openapi_schema["components"]:
        openapi_schema["components"]["securitySchemes"] = {}
    openapi_schema["components"]["securitySchemes"]["HTTPBearer"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Enter your JWT access token",
    }
    # Apply globally so all endpoints show the lock
    openapi_schema["security"] = [{"HTTPBearer": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# ─── Middleware (order matters: outermost first) ───
app.add_middleware(GZipMiddleware, minimum_size=1024)  # Compress responses > 1KB
app.add_middleware(ExceptionHandlerMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuditContextMiddleware)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ───
app.include_router(api_v1_router)


@app.get("/", tags=["Root"])
async def root() -> dict:
    """Root endpoint - application info."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }
