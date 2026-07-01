/**
 * User Management page.
 * Lists all users and provides create/edit/import functionality.
 */

import { useState } from 'react';
import { Button } from 'primereact/button';
import { Toast } from 'primereact/toast';
import { useRef } from 'react';
import { UserTable } from '../components/UserTable';
import { UserForm } from '../components/UserForm';
import { EditUserDialog } from '../components/EditUserDialog';
import { ImportEmployeeDialog } from '../components/ImportEmployeeDialog';
import { useUsers, useCreateUser, useUpdateUser } from '../hooks/useUsers';
import type { User, CreateUserRequest, UpdateUserRequest } from '../models/User';

export const UserListPage = () => {
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const toast = useRef<Toast>(null);

  const { data, isLoading } = useUsers();
  const createUserMutation = useCreateUser();
  const updateUserMutation = useUpdateUser();

  const handleCreateUser = async (formData: CreateUserRequest) => {
    try {
      await createUserMutation.mutateAsync(formData);
      setShowCreateDialog(false);
      toast.current?.show({
        severity: 'success',
        summary: 'Success',
        detail: `User '${formData.username}' created successfully`,
        life: 3000,
      });
    } catch (error: any) {
      const rawDetail = error.response?.data?.detail;
      // Handle Pydantic 422 validation errors (array of objects)
      const detail = Array.isArray(rawDetail)
        ? rawDetail.map((e: any) => e.msg || e.message).join('; ')
        : (typeof rawDetail === 'string' ? rawDetail : 'Failed to create user');
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail,
        life: 5000,
      });
    }
  };

  const handleEditUser = (user: User) => {
    setEditingUser(user);
    setShowEditDialog(true);
  };

  const handleUpdateUser = async (userId: string, formData: UpdateUserRequest) => {
    try {
      await updateUserMutation.mutateAsync({ userId, request: formData });
      setShowEditDialog(false);
      setEditingUser(null);
      toast.current?.show({
        severity: 'success',
        summary: 'Success',
        detail: 'User updated successfully',
        life: 3000,
      });
    } catch (error: any) {
      const rawDetail = error.response?.data?.detail;
      const detail = Array.isArray(rawDetail)
        ? rawDetail.map((e: any) => e.msg || e.message).join('; ')
        : (typeof rawDetail === 'string' ? rawDetail : 'Failed to update user');
      toast.current?.show({
        severity: 'error',
        summary: 'Error',
        detail,
        life: 5000,
      });
    }
  };

  return (
    <div className="p-4">
      <Toast ref={toast} />

      {/* Header */}
      <div className="flex align-items-center justify-content-between mb-4">
        <div>
          <h2 className="text-2xl font-semibold text-900 m-0">User Management</h2>
          <p className="text-600 mt-1 mb-0">Manage application users and roles</p>
        </div>
        <div className="flex gap-2">
          <Button
            label="Fetch Employee"
            icon="pi pi-download"
            severity="secondary"
            outlined
            onClick={() => setShowImportDialog(true)}
            aria-label="Fetch employees from AD"
          />
          <Button
            label="New User"
            icon="pi pi-plus"
            onClick={() => setShowCreateDialog(true)}
            aria-label="Create new user"
          />
        </div>
      </div>

      {/* Data Table */}
      <div className="surface-card p-4 border-round shadow-1">
        <UserTable
          users={data?.users || []}
          loading={isLoading}
          onEdit={handleEditUser}
        />
      </div>

      {/* Create User Dialog */}
      <UserForm
        visible={showCreateDialog}
        onHide={() => setShowCreateDialog(false)}
        onSubmit={handleCreateUser}
        loading={createUserMutation.isPending}
      />

      {/* Edit User Dialog */}
      <EditUserDialog
        visible={showEditDialog}
        user={editingUser}
        onHide={() => { setShowEditDialog(false); setEditingUser(null); }}
        onSubmit={handleUpdateUser}
        loading={updateUserMutation.isPending}
      />

      {/* Import Employee Dialog */}
      <ImportEmployeeDialog
        visible={showImportDialog}
        onHide={() => setShowImportDialog(false)}
        onSuccess={() => {
          toast.current?.show({
            severity: 'success',
            summary: 'Import Complete',
            detail: 'Employees imported successfully',
            life: 3000,
          });
        }}
      />
    </div>
  );
};
