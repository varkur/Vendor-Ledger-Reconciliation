"""Column mapping template model for persisting vendor-specific column mappings."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class ColumnMappingTemplateModel(BaseModel):
    """
    Stores column mapping templates per vendor.

    Each vendor has at most one mapping template (unique constraint on vendor_id).
    The mapping_config stores an array of column mapping objects, each containing:
    - column_index: int (position in the uploaded file)
    - header: str (original column header from the file)
    - tag: str (assigned transaction type tag)
    - confidence: str (High/Medium/Low confidence level)
    """

    __tablename__ = "vlr_column_mapping_templates"

    vendor_id: Mapped[UUID] = mapped_column(
        ForeignKey("vlr_vendors.id"), unique=True, nullable=False
    )
    mapping_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    vendor = relationship("VendorModel", lazy="noload")

    __table_args__ = (
        Index("ix_vlr_column_mapping_templates_vendor_id", "vendor_id"),
    )
