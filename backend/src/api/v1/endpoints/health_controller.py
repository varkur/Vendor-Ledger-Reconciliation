"""
Health check endpoints for Kubernetes liveness, readiness, and startup probes.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live", summary="Liveness probe")
async def liveness() -> dict:
    """Indicates the application process is running."""
    return {"status": "alive"}


@router.get("/ready", summary="Readiness probe")
async def readiness() -> dict:
    """Indicates the application is ready to accept traffic."""
    # In production, check DB connectivity, cache, etc.
    return {"status": "ready"}


@router.get("/startup", summary="Startup probe")
async def startup() -> dict:
    """Indicates the application has completed initialization."""
    return {"status": "started"}
