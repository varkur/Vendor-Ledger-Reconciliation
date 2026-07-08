"""
Document Type Mapping model for configurable document type classification.

Allows administrators to add, modify, or remove document type to category
mappings without code changes.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
"""

from sqlalchemy import Boolean, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class DocumentTypeMappingModel(BaseModel):
    """
    Configurable document type to category mapping.

    Stores the mapping between SAP document type codes (e.g., RE, KR, ZP)
    and their classification categories (e.g., Invoice, Payment, Credit Note).

    Admin-configurable: entries can be added/modified/deactivated via the
    settings UI without requiring code changes or deployments.
    """

    __tablename__ = "vlr_document_type_mappings"

    document_type_code: Mapped[str] = mapped_column(
        String(10), unique=True, nullable=False,
        comment="SAP document type code (e.g., RE, KR, DR, ZP, KZ, ZV, KG, RV)"
    )
    category: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="Classification category: Invoice, Payment, Credit Note, Debit Note, TDS, Other"
    )
    is_tds: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        comment="Whether this document type is a TDS entry"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Whether this mapping is active (allows soft-delete)"
    )

    __table_args__ = (
        Index("ix_vlr_doc_type_mappings_code", "document_type_code"),
        Index("ix_vlr_doc_type_mappings_category", "category"),
        Index("ix_vlr_doc_type_mappings_active", "is_active"),
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentTypeMappingModel("
            f"code={self.document_type_code!r}, "
            f"category={self.category!r}, "
            f"is_tds={self.is_tds}, "
            f"is_active={self.is_active})>"
        )
