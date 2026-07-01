"""Commission Claim SQLAlchemy model."""

from sqlalchemy import DateTime, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class CommissionClaimModel(BaseModel):
    """Commission Claim business entity."""

    __tablename__ = "commission_claims"

    claim_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    employee_name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    company: Mapped[str] = mapped_column(String(100), nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    region: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="DRAFT", index=True)
    workflow_instance_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
