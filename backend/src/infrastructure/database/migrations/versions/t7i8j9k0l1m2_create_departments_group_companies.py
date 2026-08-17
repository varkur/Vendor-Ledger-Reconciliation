"""create departments and group_companies lookup tables, add FK columns to user_details

Revision ID: t7i8j9k0l1m2
Revises: s6h7c8d9e0f1
Create Date: 2026-08-20

Adds the `departments` and `group_companies` normalized lookup tables used by
UserService (manual creation + Darwinbox import) to resolve/create department
and group-company references. Adds nullable `department_id` / `group_company_id`
FK columns to `user_details`, keeping the existing free-text `department` /
`group_company` string columns untouched for backward compatibility.

Uniqueness on `name` is enforced case-insensitively via a functional unique
index (lower(name)) rather than a plain unique constraint, matching the
case-insensitive get-or-create lookup semantics in UserService.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "t7i8j9k0l1m2"
down_revision: Union[str, None] = "s6h7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("modified_by", sa.String(length=255), nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_departments_name", "departments", ["name"], unique=False
    )
    op.create_index(
        "ix_departments_name_lower_unique",
        "departments",
        [sa.text("lower(name)")],
        unique=True,
    )

    op.create_table(
        "group_companies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("modified_by", sa.String(length=255), nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_group_companies_name", "group_companies", ["name"], unique=False
    )
    op.create_index(
        "ix_group_companies_name_lower_unique",
        "group_companies",
        [sa.text("lower(name)")],
        unique=True,
    )

    op.add_column(
        "user_details",
        sa.Column("department_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "user_details",
        sa.Column("group_company_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_user_details_department_id",
        "user_details",
        "departments",
        ["department_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_user_details_group_company_id",
        "user_details",
        "group_companies",
        ["group_company_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_user_details_group_company_id", "user_details", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_user_details_department_id", "user_details", type_="foreignkey"
    )
    op.drop_column("user_details", "group_company_id")
    op.drop_column("user_details", "department_id")

    op.drop_index("ix_group_companies_name_lower_unique", table_name="group_companies")
    op.drop_index("ix_group_companies_name", table_name="group_companies")
    op.drop_table("group_companies")

    op.drop_index("ix_departments_name_lower_unique", table_name="departments")
    op.drop_index("ix_departments_name", table_name="departments")
    op.drop_table("departments")
