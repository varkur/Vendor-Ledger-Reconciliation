"""
Legacy Employee Import endpoint (deprecated).

Kept for backward compatibility with existing callers of
`POST /api/v1/users/import-employees`. Delegates entirely to
`UserService.import_from_darwinbox` (the corrected implementation used by
the canonical `POST /api/v1/users/import` endpoint) — no inline user/role
creation logic lives here anymore.

The previous implementation directly constructed `UserModel(role="USER", ...)`,
which referenced a nonexistent `role` column and never created RBAC
`role_assignments` rows. That bug is fixed by delegating to UserService.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user, get_user_repository
from src.api.v1.schemas.user_request import ImportFromDarwinboxRequest
from src.application.services.user_service import UserService
from src.domain.entities.user import User
from src.domain.exceptions.domain_exceptions import ConfigurationError
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.database.session import get_db_session
from src.infrastructure.external.employee_ad.employee_ad_client import (
    EmployeeADError,
    EmployeeADUnavailableError,
)
from src.infrastructure.security.permission_manager import require_permission

router = APIRouter(prefix="/users", tags=["Users"])

logger = logging.getLogger(__name__)


def _get_user_service(
    session: AsyncSession = Depends(get_db_session),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> UserService:
    """FastAPI dependency — creates UserService with injected dependencies."""
    return UserService(session=session, user_repo=user_repo)


class ImportEmployeesRequest(BaseModel):
    """Request body for importing employees from Darwin AD (legacy contract)."""

    employee_ids: list[str] = Field(..., description="List of employee IDs to import")


class ImportResult(BaseModel):
    """Result for a single employee import."""

    employee_id: str
    status: str  # "created", "updated", "failed"
    message: str = ""


class ImportEmployeesResponse(BaseModel):
    """Response for the import operation (legacy contract, preserved)."""

    total: int
    created: int
    updated: int
    failed: int
    results: list[ImportResult]


@router.post(
    "/import-employees",
    response_model=ImportEmployeesResponse,
    summary="Import employees from Darwin AD (deprecated — use POST /users/import)",
    deprecated=True,
    dependencies=[Depends(require_permission("users.import"))],
)
async def import_employees(
    request: ImportEmployeesRequest,
    current_user: User = Depends(get_current_active_user),
    service: UserService = Depends(_get_user_service),
    user_repo: IUserRepository = Depends(get_user_repository),
) -> ImportEmployeesResponse:
    """
    Deprecated. Delegates each employee_id to `UserService.import_from_darwinbox`.

    - New users: created via UserService with is_validate_ad=True and the
      DARWINBOX_DEFAULT_PASSWORD-derived hash — never a raw `role` column write.
    - Existing users: password unchanged; user_details + RBAC role assignment
      are refreshed/ensured via UserService, same as the canonical endpoint.

    Per Req 3.1, a delegation failure is treated as fatal to the whole request
    (no per-item soft failure, no fallback to the old broken inline logic).
    """
    results: list[ImportResult] = []
    created_count = 0
    updated_count = 0
    failed_count = 0

    for emp_id in request.employee_ids:
        emp_id = emp_id.strip()
        if not emp_id:
            failed_count += 1
            results.append(ImportResult(
                employee_id="unknown",
                status="failed",
                message="Empty employee_id in request",
            ))
            continue

        try:
            existed_before = await user_repo.exists_by_username(emp_id)
            await service.import_from_darwinbox(
                ImportFromDarwinboxRequest(employee_id=emp_id), actor=current_user
            )
            if existed_before:
                updated_count += 1
                results.append(ImportResult(employee_id=emp_id, status="updated"))
            else:
                created_count += 1
                results.append(ImportResult(employee_id=emp_id, status="created"))
        except (ConfigurationError, EmployeeADError, EmployeeADUnavailableError) as exc:
            # Fatal per Req 3.1 — fail the entire request, no fallback logic.
            logger.error("Legacy import-employees delegation failed for employee_id=%s: %s", emp_id, exc)
            raise HTTPException(status_code=502, detail=f"Import failed: {exc}")
        except ValueError as exc:
            # Not-found / invalid data for this employee — also fatal to the whole
            # request per Req 3.1 (no per-item soft failure).
            logger.error("Legacy import-employees delegation failed for employee_id=%s: %s", emp_id, exc)
            raise HTTPException(status_code=404, detail=f"Import failed for '{emp_id}': {exc}")

    return ImportEmployeesResponse(
        total=len(results),
        created=created_count,
        updated=updated_count,
        failed=failed_count,
        results=results,
    )
