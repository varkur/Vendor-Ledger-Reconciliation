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
from src.api.v1.endpoints.vlr.vendor_controller import router as vlr_vendor_router
from src.api.v1.endpoints.vlr.sap_settings_controller import router as vlr_sap_settings_router
from src.api.v1.endpoints.vlr.settings_controller import router as vlr_settings_router
from src.api.v1.endpoints.vlr.sap_pull_controller import router as vlr_sap_pull_router
from src.api.v1.endpoints.vlr.request_controller import router as vlr_request_router
from src.api.v1.endpoints.vlr.case_controller import router as vlr_case_router
from src.api.v1.endpoints.vlr.exception_controller import router as vlr_exception_router
from src.api.v1.endpoints.vlr.approval_controller import router as vlr_approval_router
from src.api.v1.endpoints.vlr.notification_controller import router as vlr_notification_router
from src.api.v1.endpoints.vlr.portal_controller import router as vlr_portal_router
from src.api.v1.endpoints.vlr.report_controller import router as vlr_report_router
from src.api.v1.endpoints.vlr.transformation_controller import router as vlr_transformation_router
from src.api.v1.endpoints.vlr.column_mapping_controller import router as vlr_column_mapping_router
from src.api.v1.endpoints.vlr.workflow_controller import router as vlr_workflow_router
from src.api.v1.endpoints.vlr.reconciliation_output_controller import router as vlr_reconciliation_output_router
from src.api.v1.endpoints.vlr.dashboard_controller import router as vlr_dashboard_router
from src.api.v1.endpoints.vlr.recovery_controller import router as vlr_recovery_router
from src.api.v1.endpoints.vlr.audit_controller import router as vlr_audit_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(auth_router)
api_v1_router.include_router(user_router)
api_v1_router.include_router(rbac_router)
api_v1_router.include_router(employee_import_router)
api_v1_router.include_router(health_router)
api_v1_router.include_router(employee_ad_router)
api_v1_router.include_router(workflow_router)
api_v1_router.include_router(claims_router)
api_v1_router.include_router(vlr_vendor_router)
api_v1_router.include_router(vlr_sap_settings_router)
api_v1_router.include_router(vlr_settings_router)
api_v1_router.include_router(vlr_sap_pull_router)
api_v1_router.include_router(vlr_request_router)
api_v1_router.include_router(vlr_case_router)
api_v1_router.include_router(vlr_exception_router)
api_v1_router.include_router(vlr_approval_router)
api_v1_router.include_router(vlr_notification_router)
api_v1_router.include_router(vlr_portal_router)
api_v1_router.include_router(vlr_report_router)
api_v1_router.include_router(vlr_transformation_router)
api_v1_router.include_router(vlr_column_mapping_router)
api_v1_router.include_router(vlr_workflow_router)
api_v1_router.include_router(vlr_reconciliation_output_router)
api_v1_router.include_router(vlr_dashboard_router)
api_v1_router.include_router(vlr_recovery_router)
api_v1_router.include_router(vlr_audit_router)
