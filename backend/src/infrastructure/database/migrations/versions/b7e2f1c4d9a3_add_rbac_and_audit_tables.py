"""add_rbac_and_audit_tables

Revision ID: b7e2f1c4d9a3
Revises: a5aa03181478
Create Date: 2026-06-18 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'b7e2f1c4d9a3'
down_revision: Union[str, None] = 'a5aa03181478'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tenants table
    op.create_table(
        'tenants',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('domain', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('settings', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('created_by', sa.String(255), nullable=False, server_default='system'),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('modified_by', sa.String(255), nullable=False, server_default='system'),
        sa.Column('modified_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_tenants_code', 'tenants', ['code'], unique=True)
    op.create_index('ix_tenants_domain', 'tenants', ['domain'])

    # Permissions table
    op.create_table(
        'permissions',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('code', sa.String(100), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('scope', sa.String(20), nullable=False),
        sa.Column('resource', sa.String(255), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_by', sa.String(255), nullable=False, server_default='system'),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('modified_by', sa.String(255), nullable=False, server_default='system'),
        sa.Column('modified_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_permissions_code', 'permissions', ['code'], unique=True)
    op.create_index('ix_permissions_scope', 'permissions', ['scope'])
    op.create_index('ix_permissions_resource', 'permissions', ['resource'])

    # Roles table
    op.create_table(
        'roles',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=True),
        sa.Column('parent_role_id', UUID(as_uuid=True), nullable=True),
        sa.Column('created_by', sa.String(255), nullable=False, server_default='system'),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('modified_by', sa.String(255), nullable=False, server_default='system'),
        sa.Column('modified_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['parent_role_id'], ['roles.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_roles_code', 'roles', ['code'], unique=True)
    op.create_index('ix_roles_tenant_id', 'roles', ['tenant_id'])

    # Role-Permission association table
    op.create_table(
        'role_permissions',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('role_id', UUID(as_uuid=True), nullable=False),
        sa.Column('permission_id', UUID(as_uuid=True), nullable=False),
        sa.Column('created_by', sa.String(255), nullable=False, server_default='system'),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('modified_by', sa.String(255), nullable=False, server_default='system'),
        sa.Column('modified_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_role_permissions_role_id', 'role_permissions', ['role_id'])
    op.create_index('ix_role_permissions_permission_id', 'role_permissions', ['permission_id'])

    # Role Assignments table (User ↔ Role, tenant-scoped)
    op.create_table(
        'role_assignments',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('role_id', UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_by', sa.String(255), nullable=False, server_default='system'),
        sa.Column('created_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('modified_by', sa.String(255), nullable=False, server_default='system'),
        sa.Column('modified_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_role_assignments_user_id', 'role_assignments', ['user_id'])
    op.create_index('ix_role_assignments_role_id', 'role_assignments', ['role_id'])
    op.create_index('ix_role_assignments_tenant_id', 'role_assignments', ['tenant_id'])

    # Audit Logs table (append-only, immutable)
    op.create_table(
        'audit_logs',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('actor_id', UUID(as_uuid=True), nullable=True),
        sa.Column('actor_username', sa.String(255), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('resource_type', sa.String(100), nullable=False),
        sa.Column('resource_id', sa.String(100), nullable=False, server_default=''),
        sa.Column('tenant_id', UUID(as_uuid=True), nullable=True),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=False, server_default=''),
        sa.Column('user_agent', sa.String(512), nullable=False, server_default=''),
        sa.Column('extra_data', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_logs_actor_id', 'audit_logs', ['actor_id'])
    op.create_index('ix_audit_logs_actor_username', 'audit_logs', ['actor_username'])
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_audit_logs_resource_type', 'audit_logs', ['resource_type'])
    op.create_index('ix_audit_logs_tenant_id', 'audit_logs', ['tenant_id'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])

    # Seed system roles
    op.execute("""
        INSERT INTO roles (id, code, name, description, is_system, is_active, created_by, modified_by, created_date, modified_date)
        VALUES
            (gen_random_uuid(), 'ADMIN', 'Administrator', 'Full system access', true, true, 'migration', 'migration', NOW(), NOW()),
            (gen_random_uuid(), 'MANAGER', 'Manager', 'Department management access', true, true, 'migration', 'migration', NOW(), NOW()),
            (gen_random_uuid(), 'USER', 'Standard User', 'Basic application access', true, true, 'migration', 'migration', NOW(), NOW())
    """)


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('role_assignments')
    op.drop_table('role_permissions')
    op.drop_table('roles')
    op.drop_table('permissions')
    op.drop_table('tenants')
