"""
Employee Import endpoint.
Fetches employees from Darwin AD service and upserts them into users + user_details tables.

Flow:
1. Accept comma-separated employee IDs
2. Call Darwin /getselectedemployees
3. For each employee:
   - If user exists (username == employee_id): skip password, upsert user_details
   - If user doesn't exist: create user with default password = employee_id, create user_details
"""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_current_active_user
from src.domain.entities.user import User
from src.infrastructure.database.models.user_details_model import UserDetailsModel
from src.infrastructure.database.models.user_model import UserModel
from src.infrastructure.database.session import get_db_session
from src.infrastructure.external.employee_ad.employee_ad_client import (
    EmployeeADClient,
    EmployeeADError,
)
from src.infrastructure.security.password_encoder import hash_password
from src.infrastructure.security.permission_manager import require_permission

router = APIRouter(prefix="/users", tags=["Users"])

_ad_client = EmployeeADClient()


class ImportEmployeesRequest(BaseModel):
    """Request body for importing employees from Darwin AD."""

    employee_ids: list[str] = Field(..., description="List of employee IDs to import")


class ImportResult(BaseModel):
    """Result for a single employee import."""

    employee_id: str
    status: str  # "created", "updated", "failed"
    message: str = ""


class ImportEmployeesResponse(BaseModel):
    """Response for the import operation."""

    total: int
    created: int
    updated: int
    failed: int
    results: list[ImportResult]


@router.post(
    "/import-employees",
    response_model=ImportEmployeesResponse,
    summary="Import employees from Darwin AD",
    dependencies=[Depends(require_permission("users.import"))],
)
async def import_employees(
    request: ImportEmployeesRequest,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> ImportEmployeesResponse:
    """
    Fetch employees from Darwin AD and upsert into users + user_details.

    - New users: created with username=employee_id, password=employee_id, role=USER
    - Existing users: password unchanged, user_details updated with latest Darwin data
    """
    # 1. Fetch from Darwin
    try:
        darwin_response = await _ad_client.get_selected_employees(request.employee_ids)
    except EmployeeADError as exc:
        raise HTTPException(status_code=502, detail=f"Darwin API error: {exc.detail}")

    import logging
    logger = logging.getLogger(__name__)
    logger.info("Darwin raw response keys: %s", darwin_response.keys() if isinstance(darwin_response, dict) else type(darwin_response))
    logger.info("Darwin raw response (first 1000 chars): %s", str(darwin_response)[:1000])

    employee_data_list = darwin_response.get("employeeData", [])
    if not employee_data_list:
        # Maybe response uses different key — try the whole response if it's a list
        if isinstance(darwin_response, list):
            employee_data_list = darwin_response
        else:
            # Try other common keys
            for key in darwin_response:
                val = darwin_response[key]
                if isinstance(val, list) and len(val) > 0:
                    employee_data_list = val
                    break

    results: list[ImportResult] = []
    created_count = 0
    updated_count = 0
    failed_count = 0

    for emp_data in employee_data_list:
        logger.info("Employee data keys: %s", emp_data.keys() if isinstance(emp_data, dict) else type(emp_data))
        logger.info("Employee data sample: %s", str(emp_data)[:500])
        emp_id = str(
            emp_data.get("employee_id", emp_data.get("EmployeeId", emp_data.get("employeeId", "")))
        ).strip()
        if not emp_id:
            failed_count += 1
            results.append(ImportResult(
                employee_id="unknown",
                status="failed",
                message="No EmployeeId in Darwin response",
            ))
            continue

        try:
            # 2. Check if user exists
            stmt = select(UserModel).where(UserModel.username == emp_id)
            result = await session.execute(stmt)
            user_model = result.scalar_one_or_none()

            if user_model is None:
                # Create new user
                user_model = UserModel(
                    id=uuid4(),
                    username=emp_id,
                    password_hash=hash_password(emp_id),
                    is_active=True,
                    is_blocked=False,
                    role="USER",
                    created_by=current_user.username,
                    modified_by=current_user.username,
                )
                session.add(user_model)
                await session.flush()
                status_str = "created"
                created_count += 1
            else:
                status_str = "updated"
                updated_count += 1

            # 3. Upsert user_details
            details_stmt = select(UserDetailsModel).where(
                UserDetailsModel.user_id == user_model.id
            )
            details_result = await session.execute(details_stmt)
            details_model = details_result.scalar_one_or_none()

            details_fields = _extract_details_fields(emp_data, user_model.id, current_user.username)

            if details_model is None:
                details_model = UserDetailsModel(**details_fields)
                session.add(details_model)
            else:
                # Update existing details
                for key, value in details_fields.items():
                    if key not in ("id", "user_id", "created_by", "created_date"):
                        setattr(details_model, key, value)
                details_model.modified_by = current_user.username

            await session.flush()
            results.append(ImportResult(employee_id=emp_id, status=status_str))

        except Exception as exc:
            failed_count += 1
            results.append(ImportResult(
                employee_id=emp_id,
                status="failed",
                message=str(exc)[:200],
            ))

    return ImportEmployeesResponse(
        total=len(results),
        created=created_count,
        updated=updated_count,
        failed=failed_count,
        results=results,
    )


def _extract_details_fields(emp_data: dict, user_id, created_by: str) -> dict:
    """Extract and normalize Darwin employee fields into user_details columns."""
    # Darwin uses snake_case keys
    def get(key: str) -> str:
        val = emp_data.get(key, "")
        return str(val).strip() if val is not None else ""

    first = get("first_name")
    middle = get("middle_name")
    last = get("last_name")
    full_name = " ".join(part for part in [first, middle, last] if part)

    return {
        "id": uuid4(),
        "user_id": user_id,
        "employee_id": get("employee_id"),
        "employee_name": full_name,
        "first_name": first,
        "middle_name": middle,
        "last_name": last,
        "email": get("company_email_id"),
        "designation_title": get("designation_title"),
        "department": get("department"),
        "business_unit": get("business_unit"),
        "group_company": get("group_company"),
        "location": get("office_location"),
        "region": get("office_state"),
        "zone": get("office_city"),
        "grade": get("job_level"),
        "office_mobile_no": get("office_mobile_no"),
        "personal_mobile_no": get("personal_mobile_no"),
        "date_of_joining": get("date_of_joining") or get("date_of_birth"),
        "reporting_manager": get("direct_manager_name"),
        "direct_manager_employee_id": get("direct_manager_employee_id"),
        "direct_manager_name": get("direct_manager_name"),
        "direct_manager_email": get("direct_manager_email"),
        "sap_user_id": get("cost_center_id"),
        "division_id": get("division"),
        "territory_id": get("territory_code_(sales_hq_code)"),
        "created_by": created_by,
        "modified_by": created_by,
    }
