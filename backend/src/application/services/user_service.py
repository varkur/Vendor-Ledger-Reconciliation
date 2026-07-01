"""
User Application Service.
Orchestrates user business logic — CRUD, role assignment, details, history.
Controllers delegate here; this layer calls repositories.
"""

from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.v1.schemas.user_request import CreateUserRequest, UpdateUserRequest
from src.api.v1.schemas.user_response import UserDetailResponse, UserListResponse, UserResponse
from src.domain.entities.user import User
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.database.models.audit_log_model import AuditLogModel
from src.infrastructure.database.models.role_model import RoleAssignmentModel, RoleModel
from src.infrastructure.database.models.user_details_model import UserDetailsModel
from src.infrastructure.database.models.user_model import UserModel
from src.infrastructure.security.password_encoder import hash_password


class UserService:
    """
    Application service for user management.

    Responsibilities:
    - Orchestrate user CRUD operations
    - Manage role assignments
    - Aggregate data from multiple sources (users, user_details, audit_logs)
    """

    def __init__(self, session: AsyncSession, user_repo: IUserRepository) -> None:
        self._session = session
        self._user_repo = user_repo

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

    # ─── Create User ───

    async def create_user(self, request: CreateUserRequest, actor: User) -> UserResponse:
        """Create a new user and optionally assign a role."""
        if await self._user_repo.exists_by_username(request.username):
            raise ValueError(f"Username '{request.username}' already exists")

        user = User(
            id=uuid4(),
            username=request.username,
            password_hash=hash_password(request.password),
            is_validate_ad=request.is_validate_ad,
            created_by=actor.username,
            modified_by=actor.username,
        )

        created = await self._user_repo.create(user)

        # Assign role if provided
        if request.role_id:
            await self._assign_role(created.id, request.role_id, actor.username)

        return self._to_response(created)

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

    # ─── Private Helpers ───

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

    @staticmethod
    def _to_response(user: User) -> UserResponse:
        """Map domain entity to response DTO."""
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
