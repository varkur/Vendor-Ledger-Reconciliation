"""
User Application Service.
Orchestrates user business logic — CRUD, role assignment, details, history,
manual full-profile creation, and Darwinbox/AD import.
Controllers delegate here; this layer calls repositories.
"""

import logging
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.v1.schemas.user_request import (
    CreateUserRequest,
    ImportFromDarwinboxRequest,
    UpdateUserRequest,
)
from src.api.v1.schemas.user_response import UserDetailResponse, UserListResponse, UserResponse
from src.config.settings import settings
from src.domain.entities.user import User
from src.domain.exceptions.domain_exceptions import ConfigurationError
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.database.models.audit_log_model import AuditLogModel
from src.infrastructure.database.models.department_model import DepartmentModel
from src.infrastructure.database.models.group_company_model import GroupCompanyModel
from src.infrastructure.database.models.role_model import RoleAssignmentModel, RoleModel
from src.infrastructure.database.models.user_details_model import UserDetailsModel
from src.infrastructure.database.models.user_model import UserModel
from src.infrastructure.external.employee_ad.employee_ad_client import EmployeeADClient
from src.infrastructure.security.password_encoder import hash_password

logger = logging.getLogger(__name__)


class UserService:
    """
    Application service for user management.

    Responsibilities:
    - Orchestrate user CRUD operations
    - Manage role assignments
    - Aggregate data from multiple sources (users, user_details, audit_logs)
    - Provision users manually with a full profile
    - Import users from Darwinbox/AD by employee ID (idempotent, RBAC-correct)

    Logging safety: this service MUST NOT log plaintext passwords (explicit,
    resolved, or the DARWINBOX_DEFAULT_PASSWORD default) or raw Darwin PII
    payloads. Only non-sensitive identifiers (employee_id, username) are logged.
    """

    def __init__(
        self,
        session: AsyncSession,
        user_repo: IUserRepository,
        ad_client: EmployeeADClient | None = None,
    ) -> None:
        self._session = session
        self._user_repo = user_repo
        self._ad_client = ad_client if ad_client is not None else EmployeeADClient()

    # ─── List Users ───

    async def list_users(self, skip: int = 0, limit: int = 100) -> UserListResponse:
        """Get users with employee details and last login timestamp."""
        # Query users with LEFT JOIN to user_details
        stmt = (
            select(UserModel, UserDetailsModel)
            .outerjoin(UserDetailsModel, UserDetailsModel.user_id == UserModel.id)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = result.all()

        # Get last login for each user in one batch query
        user_ids = [str(row[0].id) for row in rows]
        last_login_map = await self._get_last_logins(user_ids)

        users = []
        for user_model, details_model in rows:
            users.append(UserResponse(
                id=user_model.id,
                username=user_model.username,
                is_active=user_model.is_active,
                is_blocked=user_model.is_blocked,
                is_validate_ad=user_model.is_validate_ad,
                employee_id=details_model.employee_id if details_model else None,
                employee_name=details_model.employee_name if details_model else None,
                email=details_model.email if details_model else None,
                last_login=last_login_map.get(str(user_model.id)),
                created_by=user_model.created_by,
                created_date=user_model.created_date,
                modified_by=user_model.modified_by,
                modified_date=user_model.modified_date,
            ))

        return UserListResponse(users=users, total=len(users), skip=skip, limit=limit)

    # ─── Create User (manual, full profile) ───

    async def create_user(self, request: CreateUserRequest, actor: User) -> UserResponse:
        """
        Create a new user with full profile data and optional role assignment.

        PRECONDITIONS:
          - request.username is unique (checked below)
          - request.role_id, if provided, references an existing active role

        POSTCONDITIONS:
          - Exactly one row exists in `users` with username == request.username
          - Exactly one row exists in `user_details` with user_id == new user's id
          - If request.role_id set: exactly one active role_assignments row for (user, role)
          - Returned UserResponse never includes password_hash or plaintext password
        """
        if await self._user_repo.exists_by_username(request.username):
            raise ValueError(f"Username '{request.username}' already exists")

        # Validate role_id up front so an invalid role never results in a
        # partially-created user (Req 1.9).
        if request.role_id is not None:
            role = await self._get_role_by_id(request.role_id)
            if role is None:
                raise ValueError(f"Role '{request.role_id}' does not exist or is not active")

        password_hash = await self._resolve_password_hash(request.password)

        user = User(
            id=uuid4(),
            username=request.username,
            password_hash=password_hash,
            is_validate_ad=request.is_validate_ad,
            created_by=actor.username,
            modified_by=actor.username,
        )
        created = await self._user_repo.create(user)

        department = await self._get_or_create_department(request.department)

        details = UserDetailsModel(
            id=uuid4(),
            user_id=created.id,
            employee_id=request.employee_id or request.username,
            employee_name=request.name,
            email=str(request.email),
            designation_title=request.designation_title,
            department=request.department,
            department_id=department.id,
            reporting_manager=request.reporting_manager,
            created_by=actor.username,
            modified_by=actor.username,
        )
        self._session.add(details)

        if request.role_id:
            await self._assign_role(created.id, request.role_id, actor.username)

        await self._session.flush()
        logger.info("Created user username=%s id=%s", created.username, created.id)
        return self._to_response(created)

    # ─── Darwinbox / AD Import ───

    async def import_from_darwinbox(
        self, request: ImportFromDarwinboxRequest, actor: User
    ) -> UserResponse:
        """
        Import (create-or-update) a single user from Darwinbox/AD by employee ID.

        PRECONDITIONS:
          - request.employee_id is non-empty
          - settings.DARWINBOX_DEFAULT_ROLE_CODE resolves to an existing active role
            (checked before any writes — fail fast, no partial state)

        POSTCONDITIONS:
          - A `users` row exists with username == employee_id and is_validate_ad == True
          - A `user_details` row exists for that user, populated from Darwin's response
          - `departments` / `group_companies` rows exist for the employee's org data
            (idempotent — no duplicates on re-import)
          - The default role is assigned exactly once (idempotent)
          - If the user already existed, its password_hash is left untouched
        """
        default_role = await self._get_role_by_code(settings.DARWINBOX_DEFAULT_ROLE_CODE)
        if default_role is None:
            raise ConfigurationError(
                f"Default import role '{settings.DARWINBOX_DEFAULT_ROLE_CODE}' not found or inactive"
            )

        logger.info("Importing employee from Darwinbox: employee_id=%s", request.employee_id)
        darwin_response = await self._ad_client.get_selected_employees([request.employee_id])
        employee_data = self._extract_single_employee(darwin_response, request.employee_id)
        if employee_data is None:
            raise ValueError(f"Employee '{request.employee_id}' not found in Darwinbox")

        existing = await self._user_repo.get_by_username(request.employee_id)

        if existing is None:
            password_hash = await self._resolve_password_hash(explicit_password=None)
            new_user = User(
                id=uuid4(),
                username=request.employee_id,
                password_hash=password_hash,
                is_validate_ad=True,
                created_by=actor.username,
                modified_by=actor.username,
            )
            user = await self._user_repo.create(new_user)
        else:
            user = existing  # password_hash untouched

        await self._upsert_user_details(
            user_id=user.id,
            employee_id=request.employee_id,
            employee_data=employee_data,
            actor_username=actor.username,
        )
        await self._ensure_role_assigned(user.id, default_role.id, actor.username)

        await self._session.flush()
        logger.info("Import complete for employee_id=%s user_id=%s", request.employee_id, user.id)
        return self._to_response(user)

    # ─── Get User by ID ───

    async def get_user(self, user_id: UUID) -> User:
        """Get a user by ID. Raises ValueError if not found."""
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")
        return user

    # ─── Update User ───

    async def update_user(self, user_id: UUID, request: UpdateUserRequest, actor: User) -> UserResponse:
        """Update user properties and optionally reassign role."""
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")

        if request.is_active is not None:
            user.is_active = request.is_active
        if request.is_blocked is not None:
            user.is_blocked = request.is_blocked
        if request.is_validate_ad is not None:
            user.is_validate_ad = request.is_validate_ad

        user.mark_modified(actor.username)
        updated = await self._user_repo.update(user)

        # Update role assignment if provided (replace existing)
        if request.role_id is not None:
            await self._replace_role(user_id, request.role_id, actor.username)

        return self._to_response(updated)

    # ─── Get Full Details ───

    async def get_user_details(self, user_id: UUID) -> UserDetailResponse:
        """Get full user profile including all employee AD fields."""
        stmt = (
            select(UserModel, UserDetailsModel)
            .outerjoin(UserDetailsModel, UserDetailsModel.user_id == UserModel.id)
            .where(UserModel.id == user_id)
        )
        result = await self._session.execute(stmt)
        row = result.one_or_none()

        if not row:
            raise ValueError("User not found")

        user_model, details = row

        return UserDetailResponse(
            id=user_model.id,
            username=user_model.username,
            is_active=user_model.is_active,
            is_blocked=user_model.is_blocked,
            is_validate_ad=user_model.is_validate_ad,
            employee_id=details.employee_id if details else None,
            employee_name=details.employee_name if details else None,
            first_name=details.first_name if details else None,
            middle_name=details.middle_name if details else None,
            last_name=details.last_name if details else None,
            email=details.email if details else None,
            designation_title=details.designation_title if details else None,
            department=details.department if details else None,
            business_unit=details.business_unit if details else None,
            group_company=details.group_company if details else None,
            location=details.location if details else None,
            region=details.region if details else None,
            zone=details.zone if details else None,
            grade=details.grade if details else None,
            office_mobile_no=details.office_mobile_no if details else None,
            personal_mobile_no=details.personal_mobile_no if details else None,
            date_of_joining=details.date_of_joining if details else None,
            reporting_manager=details.reporting_manager if details else None,
            direct_manager_employee_id=details.direct_manager_employee_id if details else None,
            direct_manager_name=details.direct_manager_name if details else None,
            direct_manager_email=details.direct_manager_email if details else None,
            sap_user_id=details.sap_user_id if details else None,
            division_id=details.division_id if details else None,
            territory_id=details.territory_id if details else None,
            created_by=user_model.created_by,
            created_date=user_model.created_date,
            modified_by=user_model.modified_by,
            modified_date=user_model.modified_date,
        )

    # ─── Get User Roles ───

    async def get_user_roles(self, user_id: UUID) -> dict:
        """Get all roles and their permissions assigned to a user."""
        stmt = (
            select(RoleAssignmentModel)
            .where(
                RoleAssignmentModel.user_id == str(user_id),
                RoleAssignmentModel.is_active == True,  # noqa: E712
            )
        )
        result = await self._session.execute(stmt)
        assignments = result.scalars().all()

        if not assignments:
            return {"user_id": str(user_id), "roles": []}

        role_ids = [a.role_id for a in assignments]

        role_stmt = (
            select(RoleModel)
            .options(selectinload(RoleModel.permissions))
            .where(RoleModel.id.in_(role_ids), RoleModel.is_active == True)  # noqa: E712
        )
        role_result = await self._session.execute(role_stmt)
        roles = role_result.scalars().all()

        return {
            "user_id": str(user_id),
            "roles": [
                {
                    "id": str(role.id),
                    "code": role.code,
                    "name": role.name,
                    "permissions": [
                        {"code": p.code, "name": p.name, "scope": p.scope, "resource": p.resource, "action": p.action}
                        for p in role.permissions if p.is_active
                    ],
                }
                for role in roles
            ],
        }

    # ─── Get Login History ───

    async def get_login_history(self, user_id: UUID, limit: int = 20) -> list[dict]:
        """Get login/logout audit trail for a user."""
        # Try by actor_id first
        stmt = (
            select(AuditLogModel)
            .where(
                AuditLogModel.resource_type == "Authentication",
                AuditLogModel.actor_id == str(user_id),
            )
            .order_by(AuditLogModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        entries = result.scalars().all()

        # Fallback: try by username
        if not entries:
            user_model = await self._session.get(UserModel, str(user_id))
            if user_model:
                stmt2 = (
                    select(AuditLogModel)
                    .where(
                        AuditLogModel.resource_type == "Authentication",
                        AuditLogModel.actor_username == user_model.username,
                    )
                    .order_by(AuditLogModel.created_at.desc())
                    .limit(limit)
                )
                result = await self._session.execute(stmt2)
                entries = result.scalars().all()

        return [
            {
                "action": e.action,
                "ip_address": e.ip_address,
                "user_agent": e.user_agent,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ]

    # ─── Private Helpers: shared ───

    async def _get_last_logins(self, user_ids: list[str]) -> dict[str, str]:
        """Batch fetch last login timestamps from audit_logs."""
        if not user_ids:
            return {}

        stmt = (
            select(
                AuditLogModel.actor_id,
                func.max(AuditLogModel.created_at).label("last_login"),
            )
            .where(
                AuditLogModel.action == "LOGIN_SUCCESS",
                AuditLogModel.actor_id.in_(user_ids),
            )
            .group_by(AuditLogModel.actor_id)
        )
        result = await self._session.execute(stmt)
        return {str(row[0]): row[1] for row in result.all()}

    async def _assign_role(self, user_id: UUID, role_id: UUID, actor_username: str) -> None:
        """Assign a single role to a user."""
        assignment = RoleAssignmentModel(
            id=uuid4(),
            user_id=str(user_id),
            role_id=str(role_id),
            tenant_id=None,
            is_active=True,
            created_by=actor_username,
            modified_by=actor_username,
        )
        self._session.add(assignment)

    async def _replace_role(self, user_id: UUID, role_id: UUID, actor_username: str) -> None:
        """Replace all existing role assignments with a single new one."""
        # Deactivate existing
        existing_stmt = select(RoleAssignmentModel).where(
            RoleAssignmentModel.user_id == str(user_id),
            RoleAssignmentModel.is_active == True,  # noqa: E712
        )
        existing_result = await self._session.execute(existing_stmt)
        for assignment in existing_result.scalars().all():
            assignment.is_active = False
            assignment.modified_by = actor_username

        # Create new
        await self._assign_role(user_id, role_id, actor_username)

    async def _get_role_by_id(self, role_id: UUID) -> RoleModel | None:
        """Look up an active role by ID."""
        stmt = select(RoleModel).where(
            RoleModel.id == str(role_id),
            RoleModel.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ─── Private Helpers: password resolution (Req 1.3, 1.4, 1.5) ───

    async def _resolve_password_hash(self, explicit_password: str | None) -> str:
        """
        Resolve and hash the effective password for a new user.

        Returns the hash of `explicit_password` when provided; otherwise hashes
        `settings.DARWINBOX_DEFAULT_PASSWORD`. Raises ConfigurationError when
        neither is available (fails loudly instead of hashing an empty string).

        NOTE: never logs the plaintext password or the default password value.
        """
        if explicit_password:
            return hash_password(explicit_password)

        if not settings.DARWINBOX_DEFAULT_PASSWORD:
            raise ConfigurationError(
                "No password was supplied and DARWINBOX_DEFAULT_PASSWORD is not configured"
            )
        return hash_password(settings.DARWINBOX_DEFAULT_PASSWORD)

    # ─── Private Helpers: lookup get-or-create (Req 1.10, 2.7) ───

    async def _get_or_create_department(self, name: str | None) -> DepartmentModel:
        """
        Case-insensitive, whitespace-trimmed get-or-create for departments.
        Empty/blank names normalize to "Unspecified". Never creates two rows
        for names differing only by case/whitespace.
        """
        normalized = (name or "").strip() or "Unspecified"
        stmt = select(DepartmentModel).where(func.lower(DepartmentModel.name) == normalized.lower())
        result = await self._session.execute(stmt)
        dept = result.scalar_one_or_none()
        if dept is None:
            dept = DepartmentModel(id=uuid4(), name=normalized, is_active=True)
            self._session.add(dept)
            await self._session.flush()
        return dept

    async def _get_or_create_group_company(self, name: str | None) -> GroupCompanyModel:
        """
        Case-insensitive, whitespace-trimmed get-or-create for group companies.
        Empty/blank names normalize to "Unspecified". Never creates two rows
        for names differing only by case/whitespace.
        """
        normalized = (name or "").strip() or "Unspecified"
        stmt = select(GroupCompanyModel).where(
            func.lower(GroupCompanyModel.name) == normalized.lower()
        )
        result = await self._session.execute(stmt)
        company = result.scalar_one_or_none()
        if company is None:
            company = GroupCompanyModel(id=uuid4(), name=normalized, is_active=True)
            self._session.add(company)
            await self._session.flush()
        return company

    # ─── Private Helpers: Darwinbox import (Req 2.1-2.12) ───

    async def _get_role_by_code(self, code: str) -> RoleModel | None:
        """Look up an active role by its code (used for DARWINBOX_DEFAULT_ROLE_CODE)."""
        stmt = select(RoleModel).where(
            RoleModel.code == code,
            RoleModel.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _is_error_response(darwin_response: object) -> bool:
        """Detect a Darwin response that is error-shaped despite a successful HTTP call."""
        if not isinstance(darwin_response, dict):
            return False
        for key in ("error", "Error", "ErrorMessage", "errorMessage"):
            if key in darwin_response:
                return True
        for flag_key in ("IsSuccess", "isSuccess"):
            if darwin_response.get(flag_key) is False:
                return True
        return False

    def _extract_single_employee(self, darwin_response: object, employee_id: str) -> dict | None:
        """
        Parse Darwin's `/getselectedemployees` response and return the record
        matching `employee_id`, or None if absent or the response is error-shaped.
        """
        if self._is_error_response(darwin_response):
            return None

        employee_data_list: list = []
        if isinstance(darwin_response, dict):
            employee_data_list = darwin_response.get("employeeData", []) or []
            if not employee_data_list:
                for value in darwin_response.values():
                    if isinstance(value, list) and value:
                        employee_data_list = value
                        break
        elif isinstance(darwin_response, list):
            employee_data_list = darwin_response

        target = str(employee_id).strip()
        for emp in employee_data_list:
            if not isinstance(emp, dict):
                continue
            emp_id = str(
                emp.get("employee_id", emp.get("EmployeeId", emp.get("employeeId", "")))
            ).strip()
            if emp_id == target:
                return emp
        return None

    async def _upsert_user_details(
        self,
        user_id: UUID,
        employee_id: str,
        employee_data: dict,
        actor_username: str,
    ) -> None:
        """
        Resolve department/group_company (creating lookup rows as needed) and
        create-or-update exactly one `user_details` row for the user.

        Raises ValueError before any writes if department/group_company data
        is malformed (present but not a scalar string/number) — no partial
        resolution per Req 2.9.
        """
        department_raw = employee_data.get("department")
        group_company_raw = employee_data.get("group_company")

        for label, value in (("department", department_raw), ("group_company", group_company_raw)):
            if value is not None and not isinstance(value, (str, int, float)):
                raise ValueError(f"Malformed '{label}' value in Darwin response: {type(value).__name__}")

        department = await self._get_or_create_department(
            str(department_raw) if department_raw is not None else ""
        )
        group_company = await self._get_or_create_group_company(
            str(group_company_raw) if group_company_raw is not None else ""
        )

        details_fields = self._extract_employee_fields(
            employee_data,
            user_id=user_id,
            fallback_employee_id=employee_id,
            department_id=department.id,
            group_company_id=group_company.id,
            actor_username=actor_username,
        )

        stmt = select(UserDetailsModel).where(UserDetailsModel.user_id == user_id)
        result = await self._session.execute(stmt)
        details_model = result.scalar_one_or_none()

        if details_model is None:
            details_model = UserDetailsModel(**details_fields)
            self._session.add(details_model)
        else:
            for key, value in details_fields.items():
                if key not in ("id", "user_id", "created_by", "created_date"):
                    setattr(details_model, key, value)
            details_model.modified_by = actor_username

        await self._session.flush()

    @staticmethod
    def _extract_employee_fields(
        emp_data: dict,
        user_id: UUID,
        fallback_employee_id: str,
        department_id: UUID,
        group_company_id: UUID,
        actor_username: str,
    ) -> dict:
        """Extract and normalize Darwin employee fields into user_details columns."""

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
            "employee_id": get("employee_id") or fallback_employee_id,
            "employee_name": full_name,
            "first_name": first,
            "middle_name": middle,
            "last_name": last,
            "email": get("company_email_id"),
            "designation_title": get("designation_title"),
            "department": get("department"),
            "department_id": department_id,
            "business_unit": get("business_unit"),
            "group_company": get("group_company"),
            "group_company_id": group_company_id,
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
            "created_by": actor_username,
            "modified_by": actor_username,
        }

    async def _ensure_role_assigned(self, user_id: UUID, role_id: UUID, actor_username: str) -> None:
        """Idempotently ensure exactly one active role_assignments row exists for (user, role)."""
        stmt = select(RoleAssignmentModel).where(
            RoleAssignmentModel.user_id == str(user_id),
            RoleAssignmentModel.role_id == str(role_id),
            RoleAssignmentModel.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        if result.scalar_one_or_none() is None:
            await self._assign_role(user_id, role_id, actor_username)
            await self._session.flush()

    @staticmethod
    def _to_response(user: User) -> UserResponse:
        """Map domain entity to response DTO. Never includes password_hash."""
        return UserResponse(
            id=user.id,
            username=user.username,
            is_active=user.is_active,
            is_blocked=user.is_blocked,
            is_validate_ad=user.is_validate_ad,
            created_by=user.created_by,
            created_date=user.created_date,
            modified_by=user.modified_by,
            modified_date=user.modified_date,
        )
