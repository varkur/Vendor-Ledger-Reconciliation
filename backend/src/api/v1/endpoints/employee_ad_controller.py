"""
Employee AD Service endpoints.
Proxies requests to the Darwin AD integrator service.

Endpoints (matching Darwin OpenAPI spec):
  - GET  /health                — Check Darwin service reachability
  - POST /validate-credentials  — Validate employee AD credentials
  - POST /selected-employees    — Fetch employees by IDs
  - GET  /employees             — Get all employees
  - GET  /hierarchy             — Get hierarchy data

Protected: ADMIN role required.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.infrastructure.external.employee_ad.employee_ad_client import (
    EmployeeADClient,
    EmployeeADError,
    EmployeeADAuthError,
    EmployeeADUnavailableError,
)
from src.infrastructure.security.permission_manager import require_permission

router = APIRouter(
    prefix="/services/employee-ad",
    tags=["Employee AD Service"],
    dependencies=[Depends(require_permission("services.employee_ad"))],
)

# Singleton client instance
_client = EmployeeADClient()


class ValidateCredentialsRequest(BaseModel):
    """Request body for credential validation."""

    employee_id: str = Field(..., description="Employee ID to validate")
    password: str = Field(..., description="Employee password")


class GetSelectedEmployeesRequest(BaseModel):
    """Request body for fetching selected employees."""

    employee_ids: list[str] = Field(..., description="List of employee IDs to fetch")


def _raise_for_darwin_error(exc: EmployeeADError) -> None:
    """Map Darwin client exceptions to HTTP responses."""
    if isinstance(exc, EmployeeADAuthError):
        raise HTTPException(status_code=401, detail=exc.detail)
    if isinstance(exc, EmployeeADUnavailableError):
        raise HTTPException(status_code=503, detail=exc.detail)
    raise HTTPException(status_code=502, detail=exc.detail)


@router.get("/health", summary="Check Employee AD service reachability")
async def check_health() -> dict:
    """
    Verify whether the Darwin AD service is reachable.
    """
    result = await _client.health_check()
    return {
        "service": "Employee AD (Darwin)",
        "configured": _client.is_configured,
        "base_url": _client.base_url,
        **result,
    }


@router.post("/validate-credentials", summary="Validate employee AD credentials")
async def validate_credentials(request: ValidateCredentialsRequest) -> dict:
    """
    POST /validatecredentials — Validate employee AD credentials via Darwin.
    """
    try:
        result = await _client.validate_credentials(
            employee_id=request.employee_id,
            password=request.password,
        )
        return {
            "is_success": result.is_success,
            "is_valid_user": result.is_valid_user,
            "raw_response": result.raw_response,
        }
    except EmployeeADError as exc:
        _raise_for_darwin_error(exc)


@router.post("/selected-employees", summary="Get selected employees by IDs")
async def get_selected_employees(request: GetSelectedEmployeesRequest) -> dict:
    """
    POST /getselectedemployees — Fetch employee records by IDs (multipart/form-data to Darwin).
    """
    try:
        data = await _client.get_selected_employees(request.employee_ids)
        return data
    except EmployeeADError as exc:
        _raise_for_darwin_error(exc)


@router.get("/employees", summary="Get all employees")
async def get_employees() -> dict:
    """
    GET /getemployees — Fetch all employee records from Darwin.
    """
    try:
        data = await _client.get_employees()
        return data
    except EmployeeADError as exc:
        _raise_for_darwin_error(exc)


@router.get("/hierarchy", summary="Get hierarchy data")
async def get_hierarchy_data() -> dict:
    """
    GET /getHierarchyData — Fetch hierarchy data from Darwin.
    """
    try:
        data = await _client.get_hierarchy_data()
        return data
    except EmployeeADError as exc:
        _raise_for_darwin_error(exc)
