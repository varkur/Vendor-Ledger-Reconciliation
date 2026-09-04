/**
 * RBAC Roles Management page.
 * Lists roles and allows managing permissions via a tree with checkboxes.
 * Permissions are grouped by feature (resource) for clear visualization.
 */

import { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { Dialog } from 'primereact/dialog';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { Toolbar } from 'primereact/toolbar';
import { Tree } from 'primereact/tree';
import type { TreeNode } from 'primereact/treenode';
import type { TreeCheckboxSelectionKeys } from 'primereact/tree';
import { rbacAdminApi } from '../api/rbacAdminApi';
import type { CreateRoleRequest, Permission, Role } from '../models/rbac-admin.types';

/**
 * Build a tree structure from flat permissions, grouped by feature (resource).
 * Structure: Scope → Resource → Permission
 */
function buildPermissionTree(permissions: Permission[]): TreeNode[] {
  // Group by scope first, then by resource
  const scopeMap: Record<string, Record<string, Permission[]>> = {};

  for (const perm of permissions) {
    const scope = perm.scope;
    // Use first part of resource as feature group
    const resource = perm.resource.split('.')[0] ?? perm.resource;

    if (!scopeMap[scope]) scopeMap[scope] = {};
    const resourceMap = scopeMap[scope];
    if (!resourceMap[resource]) resourceMap[resource] = [];
    resourceMap[resource].push(perm);
  }

  const scopeLabels: Record<string, string> = {
    MENU: '📋 Menu Access',
    API: '🔌 API Access',
    FIELD: '🔒 Field-Level Access',
  };

  const scopeIcons: Record<string, string> = {
    MENU: 'pi pi-bars',
    API: 'pi pi-server',
    FIELD: 'pi pi-eye',
  };

  const tree: TreeNode[] = [];

  for (const scope of ['MENU', 'API', 'FIELD']) {
    const resources = scopeMap[scope];
    if (!resources) continue;

    const scopeNode: TreeNode = {
      key: `scope-${scope}`,
      label: scopeLabels[scope] || scope,
      icon: scopeIcons[scope],
      children: [],
      selectable: true,
    };

    for (const [resource, perms] of Object.entries(resources).sort()) {
      if (perms.length === 1 && perms[0]) {
        // Single permission under resource — add directly to scope
        const perm = perms[0];
        scopeNode.children!.push({
          key: perm.id,
          label: `${perm.name}`,
          data: perm,
          icon: 'pi pi-key',
        });
      } else {
        // Multiple permissions — group under resource node
        const resourceNode: TreeNode = {
          key: `resource-${scope}-${resource}`,
          label: resource.charAt(0).toUpperCase() + resource.slice(1),
          icon: 'pi pi-folder',
          children: perms.map((perm) => ({
            key: perm.id,
            label: `${perm.name} (${perm.action})`,
            data: perm,
            icon: 'pi pi-key',
          })),
          selectable: true,
        };
        scopeNode.children!.push(resourceNode);
      }
    }

    tree.push(scopeNode);
  }

  return tree;
}

/**
 * Convert selected permission IDs to TreeCheckboxSelectionKeys format.
 * Also marks parent nodes as checked/partial based on children.
 */
function buildSelectionKeys(
  selectedIds: Set<string>,
  tree: TreeNode[]
): TreeCheckboxSelectionKeys {
  const keys: TreeCheckboxSelectionKeys = {};

  for (const scopeNode of tree) {
    let allScopeSelected = true;
    let anyScopeSelected = false;

    for (const child of scopeNode.children || []) {
      if (child.children && child.children.length > 0) {
        // Resource group node
        let allResourceSelected = true;
        let anyResourceSelected = false;

        for (const leaf of child.children) {
          if (selectedIds.has(leaf.key as string)) {
            keys[leaf.key as string] = { checked: true, partialChecked: false };
            anyResourceSelected = true;
          } else {
            allResourceSelected = false;
          }
        }

        if (allResourceSelected && child.children.length > 0) {
          keys[child.key as string] = { checked: true, partialChecked: false };
          anyScopeSelected = true;
        } else if (anyResourceSelected) {
          keys[child.key as string] = { checked: false, partialChecked: true };
          anyScopeSelected = true;
          allScopeSelected = false;
        } else {
          allScopeSelected = false;
        }
      } else {
        // Direct leaf under scope
        if (selectedIds.has(child.key as string)) {
          keys[child.key as string] = { checked: true, partialChecked: false };
          anyScopeSelected = true;
        } else {
          allScopeSelected = false;
        }
      }
    }

    if (allScopeSelected && (scopeNode.children?.length ?? 0) > 0) {
      keys[scopeNode.key as string] = { checked: true, partialChecked: false };
    } else if (anyScopeSelected) {
      keys[scopeNode.key as string] = { checked: false, partialChecked: true };
    }
  }

  return keys;
}

/**
 * Extract actual permission IDs (leaf nodes) from TreeCheckboxSelectionKeys.
 */
function extractPermissionIds(
  selectionKeys: TreeCheckboxSelectionKeys,
  permissions: Permission[]
): string[] {
  const permIdSet = new Set(permissions.map((p) => p.id));
  const selected: string[] = [];

  for (const [key, value] of Object.entries(selectionKeys)) {
    if (permIdSet.has(key) && (value as any).checked) {
      selected.push(key);
    }
  }

  return selected;
}

export const RolesPage = () => {
  const toast = useRef<Toast>(null);
  const [roles, setRoles] = useState<Role[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showPermissionsDialog, setShowPermissionsDialog] = useState(false);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
  const [permissionTree, setPermissionTree] = useState<TreeNode[]>([]);
  const [selectionKeys, setSelectionKeys] = useState<TreeCheckboxSelectionKeys>({});
  const [createForm, setCreateForm] = useState<CreateRoleRequest>({
    code: '',
    name: '',
    description: '',
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [rolesData, permsData] = await Promise.all([
        rbacAdminApi.listRoles(),
        rbacAdminApi.listPermissions(),
      ]);
      setRoles(rolesData.roles);
      setPermissions(permsData);
      setPermissionTree(buildPermissionTree(permsData));
    } catch (error: any) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: error.response?.data?.detail || 'Failed to load RBAC data',
        life: 5000,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleCreateRole = async () => {
    try {
      await rbacAdminApi.createRole(createForm);
      setShowCreateDialog(false);
      setCreateForm({ code: '', name: '', description: '' });
      toast.current?.show({
        severity: 'success',
        summary: 'Success',
        detail: `Role '${createForm.code}' created`,
        life: 3000,
      });
      loadData();
    } catch (error: any) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: error.response?.data?.detail || 'Failed to create role',
        life: 5000,
      });
    }
  };

  const openPermissionsDialog = (role: Role) => {
    setSelectedRole(role);
    const selectedIds = new Set(role.permissions.map((p) => p.id));
    setSelectionKeys(buildSelectionKeys(selectedIds, permissionTree));
    setShowPermissionsDialog(true);
  };

  const handleSavePermissions = async () => {
    if (!selectedRole) return;

    const newPermIds = new Set(extractPermissionIds(selectionKeys, permissions));
    const currentPermIds = new Set(selectedRole.permissions.map((p) => p.id));

    // Permissions to grant (in new but not in current)
    const toGrant = [...newPermIds].filter((id) => !currentPermIds.has(id));
    // Permissions to revoke (in current but not in new)
    const toRevoke = [...currentPermIds].filter((id) => !newPermIds.has(id));

    if (toGrant.length === 0 && toRevoke.length === 0) {
      setShowPermissionsDialog(false);
      return;
    }

    try {
      for (const permId of toGrant) {
        await rbacAdminApi.grantPermission({
          role_id: selectedRole.id,
          permission_id: permId,
        });
      }
      for (const permId of toRevoke) {
        await rbacAdminApi.revokePermission({
          role_id: selectedRole.id,
          permission_id: permId,
        });
      }
      setShowPermissionsDialog(false);
      toast.current?.show({
        severity: 'success',
        summary: 'Success',
        detail: `Permissions updated for '${selectedRole.code}' (+${toGrant.length} / -${toRevoke.length})`,
        life: 3000,
      });
      loadData();
    } catch (error: any) {
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail: error.response?.data?.detail || 'Failed to update permissions',
        life: 5000,
      });
    }
  };

  // ─── Column Templates ───

  const statusTemplate = (role: Role) => (
    <Tag
      value={role.is_active ? 'Active' : 'Inactive'}
      severity={role.is_active ? 'success' : 'danger'}
    />
  );

  const typeTemplate = (role: Role) => (
    <Tag
      value={role.is_system ? 'System' : 'Custom'}
      severity={role.is_system ? 'info' : 'warning'}
    />
  );

  const permissionsCountTemplate = (role: Role) => (
    <span className="font-semibold">{role.permissions.length}</span>
  );

  const actionsTemplate = (role: Role) => (
    <div className="flex gap-2">
      <Button
        icon="pi pi-shield"
        rounded
        outlined
        severity="info"
        size="small"
        tooltip="Manage Permissions"
        tooltipOptions={{ position: 'top' }}
        onClick={() => openPermissionsDialog(role)}
        aria-label={`Manage permissions for ${role.name}`}
      />
    </div>
  );

  // ─── Toolbar ───

  const leftToolbar = () => (
    <div className="flex gap-2">
      <Button
        label="New Role"
        icon="pi pi-plus"
        onClick={() => setShowCreateDialog(true)}
        aria-label="Create new role"
      />
      <Button
        label="Refresh"
        icon="pi pi-refresh"
        severity="secondary"
        outlined
        onClick={loadData}
        aria-label="Refresh roles list"
      />
    </div>
  );

  // Count selected permissions for display
  const selectedCount = extractPermissionIds(selectionKeys, permissions).length;

  return (
    <div className="p-4">
      <Toast ref={toast} />

      {/* Header */}
      <div className="mb-4">
        <h2 className="text-2xl font-semibold text-900 m-0">Roles & Permissions</h2>
        <p className="text-600 mt-1 mb-0">Manage roles, assign permissions, and configure access control</p>
      </div>

      <div className="surface-card p-4 border-round shadow-1">
        <Toolbar className="mb-4" start={leftToolbar} />

        <DataTable
          value={roles}
          loading={loading}
          stripedRows
          paginator
          rows={10}
          emptyMessage="No roles found"
        >
          <Column field="code" header="Code" sortable />
          <Column field="name" header="Name" sortable />
          <Column field="description" header="Description" />
          <Column header="Type" body={typeTemplate} />
          <Column header="Status" body={statusTemplate} />
          <Column header="Permissions" body={permissionsCountTemplate} />
          <Column header="Actions" body={actionsTemplate} style={{ width: '8rem' }} />
        </DataTable>
      </div>

      {/* ─── Create Role Dialog ─── */}
      <Dialog
        header="Create New Role"
        visible={showCreateDialog}
        style={{ width: '450px' }}
        modal
        onHide={() => setShowCreateDialog(false)}
        footer={
          <div className="flex justify-content-end gap-2">
            <Button
              label="Cancel"
              icon="pi pi-times"
              severity="secondary"
              text
              onClick={() => setShowCreateDialog(false)}
            />
            <Button
              label="Create"
              icon="pi pi-check"
              onClick={handleCreateRole}
              disabled={!createForm.code || !createForm.name}
            />
          </div>
        }
      >
        <div className="flex flex-column gap-3 mt-2">
          <div className="flex flex-column gap-2">
            <label htmlFor="role-code" className="font-medium">Code</label>
            <InputText
              id="role-code"
              value={createForm.code}
              onChange={(e) => setCreateForm({ ...createForm, code: e.target.value.toUpperCase() })}
              placeholder="e.g. SUPERVISOR"
            />
          </div>
          <div className="flex flex-column gap-2">
            <label htmlFor="role-name" className="font-medium">Name</label>
            <InputText
              id="role-name"
              value={createForm.name}
              onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
              placeholder="e.g. Supervisor"
            />
          </div>
          <div className="flex flex-column gap-2">
            <label htmlFor="role-desc" className="font-medium">Description</label>
            <InputTextarea
              id="role-desc"
              value={createForm.description}
              onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
              rows={3}
              placeholder="What this role is for..."
            />
          </div>
        </div>
      </Dialog>

      {/* ─── Manage Permissions Dialog (Tree with Checkboxes) ─── */}
      <Dialog
        header={`Permissions — ${selectedRole?.name || ''}`}
        visible={showPermissionsDialog}
        style={{ width: '650px' }}
        modal
        onHide={() => setShowPermissionsDialog(false)}
        footer={
          <div className="flex justify-content-between align-items-center">
            <span className="text-600 text-sm">
              {selectedCount} permission{selectedCount !== 1 ? 's' : ''} selected
            </span>
            <div className="flex gap-2">
              <Button
                label="Cancel"
                icon="pi pi-times"
                severity="secondary"
                text
                onClick={() => setShowPermissionsDialog(false)}
              />
              <Button
                label="Save Changes"
                icon="pi pi-check"
                onClick={handleSavePermissions}
              />
            </div>
          </div>
        }
      >
        <div className="flex flex-column gap-3 mt-2">
          <p className="text-600 m-0">
            Check/uncheck permissions by feature. Changes are audit-logged.
          </p>
          <Tree
            value={permissionTree}
            selectionMode="checkbox"
            selectionKeys={selectionKeys}
            onSelectionChange={(e) => setSelectionKeys(e.value as TreeCheckboxSelectionKeys)}
            className="w-full"
            style={{ border: 'none' }}
            filter
            filterPlaceholder="Search permissions..."
            aria-label="Permission tree with checkboxes"
          />
        </div>
      </Dialog>
    </div>
  );
};
