"""
SQLAlchemy ORM model for the GroupCompany lookup entity.
Maps to the 'group_companies' table. Normalized reference for user_details.group_company.
"""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class GroupCompanyModel(BaseModel):
    """Group company lookup table — auto-created on demand from free-text group company names."""

    __tablename__ = "group_companies"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
