"""Create workflow engine tables.

Revision ID: d1e2f3a4b5c6
Revises: c9d4e2f5a1b7
Create Date: 2026-06-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "d1e2f3a4b5c6"
down_revision = "c9d4e2f5a1b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all workflow, state machine, and approval matrix tables."""

    # Workflow Definitions
    op.create_table(
        "workflow_definitions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, server_default="", nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False, index=True),
        sa.Column("version", sa.Integer, server_default="1", nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Workflow Statuses
    op.create_table(
        "workflow_statuses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_definition_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("code", sa.String(50), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_initial", sa.Boolean, server_default="false", nullable=False),
        sa.Column("is_terminal", sa.Boolean, server_default="false", nullable=False),
        sa.Column("sequence", sa.Integer, server_default="0", nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Workflow Transitions
    op.create_table(
        "workflow_transitions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_definition_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("from_status_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("to_status_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action_code", sa.String(50), nullable=False, index=True),
        sa.Column("guard_expression", sa.Text, nullable=True),
        sa.Column("requires_comment", sa.Boolean, server_default="false", nullable=False),
        sa.Column("auto_execute", sa.Boolean, server_default="false", nullable=False),
        sa.Column("priority", sa.Integer, server_default="0", nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Workflow Actions
    op.create_table(
        "workflow_actions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_definition_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("code", sa.String(50), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("action_type", sa.String(20), nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Workflow Steps
    op.create_table(
        "workflow_steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_definition_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("from_status_id", UUID(as_uuid=True), nullable=False),
        sa.Column("to_status_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action_code", sa.String(50), nullable=False),
        sa.Column("step_type", sa.String(20), server_default="APPROVAL", nullable=False),
        sa.Column("sequence", sa.Integer, server_default="0", nullable=False),
        sa.Column("is_parallel", sa.Boolean, server_default="false", nullable=False),
        sa.Column("sla_hours", sa.Integer, server_default="0", nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Workflow Assignment Rules
    op.create_table(
        "workflow_assignment_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_step_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("assignment_type", sa.String(20), nullable=False),
        sa.Column("role_id", UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("matrix_rule_id", UUID(as_uuid=True), nullable=True),
        sa.Column("expression", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Workflow Instances (Runtime)
    op.create_table(
        "workflow_instances",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_definition_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("entity_type", sa.String(100), nullable=False, index=True),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("current_status_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("initiated_by", UUID(as_uuid=True), nullable=False),
        sa.Column("priority", sa.Integer, server_default="0", nullable=False),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_data", JSONB, server_default="{}", nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Workflow Instance Steps
    op.create_table(
        "workflow_instance_steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("instance_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("step_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), server_default="PENDING", nullable=False),
        sa.Column("assigned_to_id", UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("action_taken", sa.String(50), nullable=True),
        sa.Column("comments", sa.Text, nullable=True),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_escalated", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Workflow History (Immutable)
    op.create_table(
        "workflow_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("instance_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("from_status_id", UUID(as_uuid=True), nullable=True),
        sa.Column("to_status_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action_code", sa.String(50), nullable=False, index=True),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=True),
        sa.Column("actor_username", sa.String(255), server_default="", nullable=False),
        sa.Column("comments", sa.Text, server_default="", nullable=False),
        sa.Column("extra_data", JSONB, nullable=True),
        sa.Column("ip_address", sa.String(45), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )

    # Approval Matrices
    op.create_table(
        "approval_matrices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False, index=True),
        sa.Column("priority", sa.Integer, server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Approval Rules
    op.create_table(
        "approval_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("matrix_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("field", sa.String(100), nullable=False),
        sa.Column("operator", sa.String(20), nullable=False),
        sa.Column("value", sa.String(500), nullable=False),
        sa.Column("data_type", sa.String(20), server_default="STRING", nullable=False),
        sa.Column("logical_group", sa.String(50), server_default="default", nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Approval Conditions
    op.create_table(
        "approval_conditions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("matrix_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("condition_type", sa.String(50), nullable=False),
        sa.Column("expression", sa.Text, nullable=False),
        sa.Column("priority", sa.Integer, server_default="0", nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Approval Assignments
    op.create_table(
        "approval_assignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("matrix_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("assignment_type", sa.String(20), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("role_id", UUID(as_uuid=True), nullable=True),
        sa.Column("level", sa.Integer, server_default="1", nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Approval Delegations
    op.create_table(
        "approval_delegations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("delegator_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("delegate_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("from_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("to_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true", nullable=False),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Approval Tasks
    op.create_table(
        "approval_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("instance_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("matrix_id", UUID(as_uuid=True), nullable=True),
        sa.Column("assignee_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("level", sa.Integer, server_default="1", nullable=False),
        sa.Column("status", sa.String(20), server_default="PENDING", nullable=False, index=True),
        sa.Column("action_taken", sa.String(50), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comments", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("created_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.String(255), server_default="system", nullable=False),
        sa.Column("modified_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    """Drop all workflow tables."""
    op.drop_table("approval_tasks")
    op.drop_table("approval_delegations")
    op.drop_table("approval_assignments")
    op.drop_table("approval_conditions")
    op.drop_table("approval_rules")
    op.drop_table("approval_matrices")
    op.drop_table("workflow_history")
    op.drop_table("workflow_instance_steps")
    op.drop_table("workflow_instances")
    op.drop_table("workflow_assignment_rules")
    op.drop_table("workflow_steps")
    op.drop_table("workflow_actions")
    op.drop_table("workflow_transitions")
    op.drop_table("workflow_statuses")
    op.drop_table("workflow_definitions")
