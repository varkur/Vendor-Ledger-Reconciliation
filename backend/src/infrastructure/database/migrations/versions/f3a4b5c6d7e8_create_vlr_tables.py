"""Create VLR (Vendor Ledger Reconciliation) tables.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-07-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON


# revision identifiers, used by Alembic.
revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable btree_gist extension for exclusion constraints (period overlap prevention)
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    # ─── Vendors ───────────────────────────────────────────────────────────────
    op.create_table(
        "vlr_vendors",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_code", sa.String(50), nullable=False),
        sa.Column("company_code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("pan", sa.String(20), nullable=True),
        sa.Column("gstin", sa.String(20), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vendor_code", "company_code", name="uq_vendor_code_company_code"),
    )
    op.create_index("ix_vlr_vendors_vendor_code", "vlr_vendors", ["vendor_code"])
    op.create_index("ix_vlr_vendors_company_code", "vlr_vendors", ["company_code"])
    op.create_index("ix_vlr_vendors_status", "vlr_vendors", ["status"])

    # ─── Vendor Contacts ───────────────────────────────────────────────────────
    op.create_table(
        "vlr_vendor_contacts",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("designation", sa.String(100), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vlr_vendors.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_vlr_vendor_contacts_vendor_id", "vlr_vendor_contacts", ["vendor_id"])

    # ─── Reconciliation Requests ───────────────────────────────────────────────
    op.create_table(
        "vlr_reconciliation_requests",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("company_code", sa.String(20), nullable=False),
        sa.Column("fiscal_year", sa.String(10), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("tolerance_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("tds_percentage", sa.Numeric(5, 2), nullable=True),
        sa.Column("gst_percentage", sa.Numeric(5, 2), nullable=True),
        sa.Column("matching_preferences", JSON, nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("assigned_manager_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'in_progress', 'review', 'sign_off', 'closed')",
            name="ck_vlr_request_valid_status",
        ),
    )
    op.create_index("ix_vlr_requests_status", "vlr_reconciliation_requests", ["status"])
    op.create_index("ix_vlr_requests_company_code", "vlr_reconciliation_requests", ["company_code"])
    op.create_index("ix_vlr_requests_created_date", "vlr_reconciliation_requests", ["created_date"])

    # ─── Reconciliation Cases ──────────────────────────────────────────────────
    op.create_table(
        "vlr_reconciliation_cases",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("case_type", sa.String(20), nullable=False, server_default="batch"),
        sa.Column("status", sa.String(30), nullable=False, server_default="created"),
        sa.Column("portal_token", sa.String(255), nullable=True, unique=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("upload_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("edit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("row_10_balance", sa.Numeric(15, 2), nullable=True),
        sa.Column("match_statistics", JSON, nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["request_id"], ["vlr_reconciliation_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vlr_vendors.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "status IN ('created', 'ledger_confirmed', 'invited', 'data_received', "
            "'matching', 'matched', 'review', 'pending_approval', 'approved', "
            "'signed_off', 'closed')",
            name="ck_vlr_case_valid_status",
        ),
        sa.CheckConstraint(
            "case_type IN ('batch', 'direct')",
            name="ck_vlr_case_valid_type",
        ),
    )
    op.create_index("ix_vlr_cases_request_id", "vlr_reconciliation_cases", ["request_id"])
    op.create_index("ix_vlr_cases_vendor_id", "vlr_reconciliation_cases", ["vendor_id"])
    op.create_index("ix_vlr_cases_status", "vlr_reconciliation_cases", ["status"])
    op.create_index("ix_vlr_cases_created_date", "vlr_reconciliation_cases", ["created_date"])

    # ─── Period overlap prevention via exclusion constraint ────────────────────
    # Prevents two non-deleted cases for the same vendor from having overlapping
    # periods within the same company code. Uses daterange from the parent request.
    # This is enforced at the application layer since exclusion constraints
    # cannot span across tables (case → request for period). Instead we add
    # a unique partial index that prevents exact duplicate (vendor, request) pairs.
    op.create_index(
        "uq_vlr_cases_vendor_request",
        "vlr_reconciliation_cases",
        ["vendor_id", "request_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )

    # ─── Ledger Entries ────────────────────────────────────────────────────────
    op.create_table(
        "vlr_ledger_entries",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", UUID(as_uuid=True), nullable=False),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("document_number", sa.String(50), nullable=False),
        sa.Column("document_type", sa.String(20), nullable=True),
        sa.Column("reference_number", sa.String(100), nullable=True),
        sa.Column("posting_date", sa.Date(), nullable=False),
        sa.Column("clearing_date", sa.Date(), nullable=True),
        sa.Column("clearing_document", sa.String(50), nullable=True),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False, server_default="INR"),
        sa.Column("assignment_number", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("match_id", UUID(as_uuid=True), nullable=True),
        sa.Column("pass_number", sa.Integer(), nullable=True),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["case_id"], ["vlr_reconciliation_cases.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_vlr_ledger_entries_case_id", "vlr_ledger_entries", ["case_id"])
    op.create_index("ix_vlr_ledger_entries_side", "vlr_ledger_entries", ["side"])
    op.create_index("ix_vlr_ledger_entries_match_id", "vlr_ledger_entries", ["match_id"])
    op.create_index("ix_vlr_ledger_entries_document_number", "vlr_ledger_entries", ["document_number"])

    # ─── Match Results ─────────────────────────────────────────────────────────
    op.create_table(
        "vlr_match_results",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", UUID(as_uuid=True), nullable=False),
        sa.Column("pass_number", sa.Integer(), nullable=False),
        sa.Column("match_type", sa.String(30), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("is_confirmed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("company_entry_ids", JSON, nullable=True),
        sa.Column("vendor_entry_ids", JSON, nullable=True),
        sa.Column("matched_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("difference_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["case_id"], ["vlr_reconciliation_cases.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_vlr_match_results_case_id", "vlr_match_results", ["case_id"])
    op.create_index("ix_vlr_match_results_pass_number", "vlr_match_results", ["pass_number"])

    # ─── Reconciliation Exceptions ─────────────────────────────────────────────
    op.create_table(
        "vlr_reco_exceptions",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", UUID(as_uuid=True), nullable=False),
        sa.Column("ledger_entry_id", UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("first_flagged_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["case_id"], ["vlr_reconciliation_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ledger_entry_id"], ["vlr_ledger_entries.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low')",
            name="ck_vlr_exception_valid_severity",
        ),
    )
    op.create_index("ix_vlr_exceptions_case_id", "vlr_reco_exceptions", ["case_id"])
    op.create_index("ix_vlr_exceptions_ledger_entry_id", "vlr_reco_exceptions", ["ledger_entry_id"])
    op.create_index("ix_vlr_exceptions_severity", "vlr_reco_exceptions", ["severity"])
    op.create_index("ix_vlr_exceptions_status", "vlr_reco_exceptions", ["status"])

    # ─── Resolution Records ────────────────────────────────────────────────────
    op.create_table(
        "vlr_resolution_records",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("exception_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("resolved_by", UUID(as_uuid=True), nullable=False),
        sa.Column("resolved_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["exception_id"], ["vlr_reco_exceptions.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "action IN ('accept_company_match', 'request_document_vendor', "
            "'mark_tds_difference', 'mark_agreed_adjustment', 'write_off', 'escalate')",
            name="ck_vlr_resolution_valid_action",
        ),
    )
    op.create_index("ix_vlr_resolution_records_exception_id", "vlr_resolution_records", ["exception_id"])

    # ─── Approval Records ──────────────────────────────────────────────────────
    op.create_table(
        "vlr_approval_records",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("approver_id", UUID(as_uuid=True), nullable=False),
        sa.Column("approval_level", sa.String(30), nullable=False, server_default="manager"),
        sa.Column("decision_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["case_id"], ["vlr_reconciliation_cases.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_vlr_approval_records_case_id", "vlr_approval_records", ["case_id"])

    # ─── Notifications ─────────────────────────────────────────────────────────
    op.create_table(
        "vlr_notifications",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("recipient_email", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("template_code", sa.String(50), nullable=True),
        sa.Column("context_data", JSON, nullable=True),
        sa.Column("sent_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["case_id"], ["vlr_reconciliation_cases.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_vlr_notifications_case_id", "vlr_notifications", ["case_id"])
    op.create_index("ix_vlr_notifications_type", "vlr_notifications", ["type"])
    op.create_index("ix_vlr_notifications_status", "vlr_notifications", ["status"])

    # ─── Settings ──────────────────────────────────────────────────────────────
    op.create_table(
        "vlr_settings",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("company_code", sa.String(20), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("value_type", sa.String(20), nullable=False, server_default="string"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("validation_rules", JSON, nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vlr_settings_company_code", "vlr_settings", ["company_code"])
    op.create_index("ix_vlr_settings_key", "vlr_settings", ["key"])
    op.create_index("ix_vlr_settings_company_key", "vlr_settings", ["company_code", "key"], unique=True)

    # ─── Automation Rules ──────────────────────────────────────────────────────
    op.create_table(
        "vlr_automation_rules",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("company_code", sa.String(20), nullable=False),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column("frequency", sa.String(30), nullable=False),
        sa.Column("configuration", JSON, nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_executed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_execution", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vlr_automation_rules_company_code", "vlr_automation_rules", ["company_code"])
    op.create_index("ix_vlr_automation_rules_is_active", "vlr_automation_rules", ["is_active"])

    # ─── Automation Executions ─────────────────────────────────────────────────
    op.create_table(
        "vlr_automation_executions",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", UUID(as_uuid=True), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("error_details", JSON, nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["rule_id"], ["vlr_automation_rules.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_vlr_automation_executions_rule_id", "vlr_automation_executions", ["rule_id"])

    # ─── Portal Sign-Offs ──────────────────────────────────────────────────────
    op.create_table(
        "vlr_portal_sign_offs",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", UUID(as_uuid=True), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("statement_version", sa.String(50), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("modified_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column("modified_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["case_id"], ["vlr_reconciliation_cases.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_vlr_portal_sign_offs_case_id", "vlr_portal_sign_offs", ["case_id"])


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table("vlr_portal_sign_offs")
    op.drop_table("vlr_automation_executions")
    op.drop_table("vlr_automation_rules")
    op.drop_table("vlr_settings")
    op.drop_table("vlr_notifications")
    op.drop_table("vlr_approval_records")
    op.drop_table("vlr_resolution_records")
    op.drop_table("vlr_reco_exceptions")
    op.drop_table("vlr_match_results")
    op.drop_table("vlr_ledger_entries")
    op.drop_table("vlr_reconciliation_cases")
    op.drop_table("vlr_reconciliation_requests")
    op.drop_table("vlr_vendor_contacts")
    op.drop_table("vlr_vendors")
