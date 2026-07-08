"""Add workflow step history, SLA configurations, and workflow/balance columns to cases.

Creates vlr_workflow_step_history table for tracking step transitions.
Creates vlr_sla_configurations table for per-step SLA durations.
Adds workflow tracking columns (current_workflow_step, step_entered_at, sla_deadline, is_overdue)
and balance tracking columns to vlr_reconciliation_cases.
Seeds default SLA configurations for all workflow steps.

Revision ID: i6d7e8f9a0b1
Revises: h5c6d7e8f9a0
Create Date: 2026-07-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = "i6d7e8f9a0b1"
down_revision: Union[str, None] = "i6d7e8f9a0b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ═══════════════════════════════════════════════════════════
    # 1. Create vlr_workflow_step_history table
    # ═══════════════════════════════════════════════════════════
    op.create_table(
        "vlr_workflow_step_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "case_id",
            UUID(as_uuid=True),
            sa.ForeignKey("vlr_reconciliation_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_step",
            sa.String(30),
            nullable=True,
            comment="Previous workflow step (null for initial transition)",
        ),
        sa.Column(
            "to_step",
            sa.String(30),
            nullable=False,
            comment="Target workflow step",
        ),
        sa.Column(
            "triggered_by",
            sa.String(100),
            nullable=False,
            comment="User or system that triggered the transition",
        ),
        sa.Column(
            "triggered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Timestamp when the transition occurred",
        ),
        sa.Column(
            "sla_deadline",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="SLA deadline for the target step",
        ),
        sa.Column(
            "is_rollback",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Whether this transition is a rollback to a previous step",
        ),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column(
            "created_date",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column(
            "modified_date",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Indexes for workflow step history
    op.create_index("ix_vlr_wf_history_case_id", "vlr_workflow_step_history", ["case_id"])
    op.create_index(
        "ix_vlr_wf_history_case_triggered",
        "vlr_workflow_step_history",
        ["case_id", "triggered_at"],
    )
    op.create_index("ix_vlr_wf_history_to_step", "vlr_workflow_step_history", ["to_step"])

    # ═══════════════════════════════════════════════════════════
    # 2. Create vlr_sla_configurations table
    # ═══════════════════════════════════════════════════════════
    op.create_table(
        "vlr_sla_configurations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "step_name",
            sa.String(30),
            unique=True,
            nullable=False,
            comment="Workflow step name matching WorkflowStep enum values",
        ),
        sa.Column(
            "sla_hours",
            sa.Integer(),
            nullable=False,
            comment="Maximum allowed hours for this step before flagging as overdue",
        ),
        sa.Column(
            "escalation_email",
            sa.String(255),
            nullable=True,
            comment="Email address for SLA violation escalation notifications",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Whether this SLA configuration is active",
        ),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column(
            "created_date",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column(
            "modified_date",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_vlr_sla_config_step", "vlr_sla_configurations", ["step_name"])
    op.create_index("ix_vlr_sla_config_active", "vlr_sla_configurations", ["is_active"])

    # ═══════════════════════════════════════════════════════════
    # 3. Add workflow columns to vlr_reconciliation_cases
    # ═══════════════════════════════════════════════════════════
    op.add_column(
        "vlr_reconciliation_cases",
        sa.Column(
            "current_workflow_step",
            sa.String(30),
            nullable=True,
            comment="Current step in the 10-step workflow",
        ),
    )
    op.add_column(
        "vlr_reconciliation_cases",
        sa.Column(
            "step_entered_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when the current workflow step was entered",
        ),
    )
    op.add_column(
        "vlr_reconciliation_cases",
        sa.Column(
            "sla_deadline",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="SLA deadline for the current workflow step",
        ),
    )
    op.add_column(
        "vlr_reconciliation_cases",
        sa.Column(
            "is_overdue",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Whether the current step has exceeded its SLA deadline",
        ),
    )

    # Balance tracking columns
    op.add_column(
        "vlr_reconciliation_cases",
        sa.Column(
            "company_opening_balance",
            sa.Numeric(15, 2),
            nullable=True,
            comment="Company-side opening balance",
        ),
    )
    op.add_column(
        "vlr_reconciliation_cases",
        sa.Column(
            "company_closing_balance",
            sa.Numeric(15, 2),
            nullable=True,
            comment="Company-side closing balance",
        ),
    )
    op.add_column(
        "vlr_reconciliation_cases",
        sa.Column(
            "vendor_opening_balance",
            sa.Numeric(15, 2),
            nullable=True,
            comment="Vendor-side opening balance",
        ),
    )
    op.add_column(
        "vlr_reconciliation_cases",
        sa.Column(
            "vendor_closing_balance",
            sa.Numeric(15, 2),
            nullable=True,
            comment="Vendor-side closing balance",
        ),
    )
    op.add_column(
        "vlr_reconciliation_cases",
        sa.Column(
            "net_difference",
            sa.Numeric(15, 2),
            nullable=True,
            comment="Net difference between company and vendor",
        ),
    )

    # Closure columns
    op.add_column(
        "vlr_reconciliation_cases",
        sa.Column(
            "closure_type",
            sa.String(20),
            nullable=True,
            comment="Closure type: 'normal' or 'one_sided'",
        ),
    )
    op.add_column(
        "vlr_reconciliation_cases",
        sa.Column(
            "closure_justification",
            sa.Text(),
            nullable=True,
            comment="Justification text for one-sided closure",
        ),
    )
    op.add_column(
        "vlr_reconciliation_cases",
        sa.Column(
            "closure_approved_by",
            sa.String(100),
            nullable=True,
            comment="Recon_Manager who approved one-sided closure",
        ),
    )

    # Indexes for new columns on reconciliation_cases
    op.create_index(
        "ix_vlr_cases_workflow_step",
        "vlr_reconciliation_cases",
        ["current_workflow_step"],
    )
    op.create_index(
        "ix_vlr_cases_is_overdue",
        "vlr_reconciliation_cases",
        ["is_overdue"],
    )

    # ═══════════════════════════════════════════════════════════
    # 4. Seed default SLA configurations per workflow step
    # ═══════════════════════════════════════════════════════════
    op.execute("""
        INSERT INTO vlr_sla_configurations (id, step_name, sla_hours, escalation_email, is_active, created_by, modified_by)
        VALUES
            (gen_random_uuid(), 'initiation', 4, NULL, true, 'system', 'system'),
            (gen_random_uuid(), 'sap_pull', 2, NULL, true, 'system', 'system'),
            (gen_random_uuid(), 'transformation', 2, NULL, true, 'system', 'system'),
            (gen_random_uuid(), 'finance_review', 48, NULL, true, 'system', 'system'),
            (gen_random_uuid(), 'column_mapping', 24, NULL, true, 'system', 'system'),
            (gen_random_uuid(), 'vendor_engagement', 240, NULL, true, 'system', 'system'),
            (gen_random_uuid(), 'auto_reconciliation', 4, NULL, true, 'system', 'system'),
            (gen_random_uuid(), 'exception_resolution', 72, NULL, true, 'system', 'system'),
            (gen_random_uuid(), 'finance_approval', 48, NULL, true, 'system', 'system'),
            (gen_random_uuid(), 'vendor_sign_off', 120, NULL, true, 'system', 'system'),
            (gen_random_uuid(), 'closure', 24, NULL, true, 'system', 'system');
    """)


def downgrade() -> None:
    # Drop indexes on reconciliation_cases
    op.drop_index("ix_vlr_cases_is_overdue", table_name="vlr_reconciliation_cases")
    op.drop_index("ix_vlr_cases_workflow_step", table_name="vlr_reconciliation_cases")

    # Drop closure columns
    op.drop_column("vlr_reconciliation_cases", "closure_approved_by")
    op.drop_column("vlr_reconciliation_cases", "closure_justification")
    op.drop_column("vlr_reconciliation_cases", "closure_type")

    # Drop balance columns
    op.drop_column("vlr_reconciliation_cases", "net_difference")
    op.drop_column("vlr_reconciliation_cases", "vendor_closing_balance")
    op.drop_column("vlr_reconciliation_cases", "vendor_opening_balance")
    op.drop_column("vlr_reconciliation_cases", "company_closing_balance")
    op.drop_column("vlr_reconciliation_cases", "company_opening_balance")

    # Drop workflow columns
    op.drop_column("vlr_reconciliation_cases", "is_overdue")
    op.drop_column("vlr_reconciliation_cases", "sla_deadline")
    op.drop_column("vlr_reconciliation_cases", "step_entered_at")
    op.drop_column("vlr_reconciliation_cases", "current_workflow_step")

    # Drop SLA configurations table
    op.drop_index("ix_vlr_sla_config_active", table_name="vlr_sla_configurations")
    op.drop_index("ix_vlr_sla_config_step", table_name="vlr_sla_configurations")
    op.drop_table("vlr_sla_configurations")

    # Drop workflow step history table
    op.drop_index("ix_vlr_wf_history_to_step", table_name="vlr_workflow_step_history")
    op.drop_index(
        "ix_vlr_wf_history_case_triggered", table_name="vlr_workflow_step_history"
    )
    op.drop_index("ix_vlr_wf_history_case_id", table_name="vlr_workflow_step_history")
    op.drop_table("vlr_workflow_step_history")
