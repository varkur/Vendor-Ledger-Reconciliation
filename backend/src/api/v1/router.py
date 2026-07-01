"""
API v1 Router - aggregates all v1 endpoint routers.
"""

from fastapi import APIRouter

from src.api.v1.endpoints.auth_controller import router as auth_router
from src.api.v1.endpoints.employee_ad_controller import router as employee_ad_router
from src.api.v1.endpoints.employee_import_controller import router as employee_import_router
from src.api.v1.endpoints.health_controller import router as health_router
from src.api.v1.endpoints.rbac_controller import router as rbac_router
from src.api.v1.endpoints.user_controller import router as user_router
from src.api.v1.endpoints.workflow.workflow_controller import router as workflow_router
from src.api.v1.endpoints.commission_claim.controller import router as claims_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(auth_router)
api_v1_router.include_router(user_router)
api_v1_router.include_router(rbac_router)
api_v1_router.include_router(employee_import_router)
api_v1_router.include_router(health_router)
api_v1_router.include_router(employee_ad_router)
api_v1_router.include_router(workflow_router)
api_v1_router.include_router(claims_router)
