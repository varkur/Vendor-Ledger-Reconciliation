"""
SQLAlchemy ORM Models.

All models must be imported here so that SQLAlchemy's Base.metadata
can resolve foreign key relationships between tables at startup.
"""

from src.infrastructure.database.models.base_model import Base, BaseModel  # noqa: F401
from src.infrastructure.database.models.user_model import UserModel  # noqa: F401
from src.infrastructure.database.models.user_details_model import UserDetailsModel  # noqa: F401
from src.infrastructure.database.models.tenant_model import TenantModel  # noqa: F401
from src.infrastructure.database.models.role_model import (  # noqa: F401
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    RoleAssignmentModel,
)
from src.infrastructure.database.models.audit_log_model import AuditLogModel  # noqa: F401
