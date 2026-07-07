"""System setting/configuration model."""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base_model import BaseModel


class SettingModel(BaseModel):
    """
    System configuration key-value store.

    Scoped by company_code for multi-tenant settings.
    Stores validation rules and value type metadata.
    """

    __tablename__ = "vlr_settings"

    company_code: Mapped[str] = mapped_column(String(20), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(String(20), nullable=False, default="string")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_vlr_settings_company_code", "company_code"),
        Index("ix_vlr_settings_key", "key"),
        Index("ix_vlr_settings_company_key", "company_code", "key", unique=True),
    )
