"""
SQLAlchemy ORM model for the UserDetails entity.
Maps to the 'user_details' table. One-to-one with users table.
"""

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base_model import BaseModel


class UserDetailsModel(BaseModel):
    """User details database table — stores Darwin AD employee data."""

    __tablename__ = "user_details"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    employee_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    employee_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    first_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    middle_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    last_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    designation_title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    department: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    department_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
    )
    business_unit: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    group_company: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    group_company_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("group_companies.id", ondelete="SET NULL"),
        nullable=True,
    )
    location: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    region: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    zone: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    grade: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    office_mobile_no: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    personal_mobile_no: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    date_of_joining: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    reporting_manager: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    direct_manager_employee_id: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    direct_manager_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    direct_manager_email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    sap_user_id: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    division_id: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    territory_id: Mapped[str] = mapped_column(String(50), nullable=False, default="")
