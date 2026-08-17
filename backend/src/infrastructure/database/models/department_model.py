"""
SQLAlchemy ORM model for the Department lookup entity.
Maps to the 'departments' table. Normalized reference for user_details.department.
"""

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class DepartmentModel(BaseModel):
    """Department lookup table — auto-created on demand from free-text department names."""

    __tablename__ = "departments"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
