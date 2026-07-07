"""Vendor master record model with soft-delete support."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class VendorModel(BaseModel):
    """
    Vendor master entity.

    Supports soft-delete via is_deleted/deleted_at columns.
    Unique constraint on (vendor_code, company_code) ensures no duplicates
    within the same company.
    """

    __tablename__ = "vlr_vendors"

    vendor_code: Mapped[str] = mapped_column(String(50), nullable=False)
    company_code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    pan: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    # Soft-delete columns
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    contacts = relationship("VendorContactModel", back_populates="vendor", lazy="selectin")
    reconciliation_cases = relationship("ReconciliationCaseModel", back_populates="vendor", lazy="noload")

    __table_args__ = (
        UniqueConstraint("vendor_code", "company_code", name="uq_vendor_code_company_code"),
        Index("ix_vlr_vendors_vendor_code", "vendor_code"),
        Index("ix_vlr_vendors_company_code", "company_code"),
        Index("ix_vlr_vendors_status", "status"),
    )
