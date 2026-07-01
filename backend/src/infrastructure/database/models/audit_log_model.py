"""
SQLAlchemy ORM model for immutable audit logs.
This table is append-only — no UPDATE or DELETE operations are permitted.
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import Base


class AuditLogModel(Base):
    """
    Immutable audit log table.
    Does NOT inherit from BaseModel to avoid modifiable audit fields.
    """

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    actor_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    actor_username: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    resource_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    resource_id: Mapped[str] = mapped_column(
        String(100), nullable=False, default=""
    )
    tenant_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False, default="")
    user_agent: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    extra_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
