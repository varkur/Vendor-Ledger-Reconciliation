/**
 * Edit User Dialog.
 * Allows editing active/blocked status, AD validation, and single role assignment.
 */

import { useEffect, useState } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Dropdown } from 'primereact/dropdown';
import { InputSwitch } from 'primereact/inputswitch';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { useRoles } from '../hooks/useRoles';
import { userApi } from '../api/userApi';
import type { User, UpdateUserRequest } from '../models/User';

const editUserSchema = z.object({
  is_active: z.boolean(),
  is_blocked: z.boolean(),
  is_validate_ad: z.boolean(),
  role_id: z.string().nullable(),
});

type EditUserFormData = z.infer<typeof editUserSchema>;

interface EditUserDialogProps {
  visible: boolean;
  user: User | null;
  onHide: () => void;
  onSubmit: (userId: string, data: UpdateUserRequest) => void;
  loading?: boolean;
}

export const EditUserDialog = ({ visible, user, onHide, onSubmit, loading }: EditUserDialogProps) => {
  const { roleOptions, loading: rolesLoading } = useRoles();
  const [loadingUserRole, setLoadingUserRole] = useState(false);

  const {
    handleSubmit,
    control,
    reset,
    setValue,
  } = useForm<EditUserFormData>({
    resolver: zodResolver(editUserSchema),
    defaultValues: {
      is_active: true,
      is_blocked: false,
      is_validate_ad: true,
      role_id: null,
    },
  });

  // Reset form and load user's current role when dialog opens
  useEffect(() => {
    if (user && visible) {
      reset({
        is_active: user.is_active,
        is_blocked: user.is_blocked,
        is_validate_ad: user.is_validate_ad,
        role_id: null,
      });

      // Fetch user's current role assignment
      setLoadingUserRole(true);
      userApi.getUserRoles(user.id)
        .then((data) => {
          const firstRole = data.roles[0];
          if (firstRole) {
            setValue('role_id', firstRole.id);
          }
        })
        .catch(() => {})
        .finally(() => setLoadingUserRole(false));
    }
  }, [user, visible, reset, setValue]);

  const handleFormSubmit = (data: EditUserFormData) => {
    if (!user) return;
    onSubmit(user.id, {
      is_active: data.is_active,
      is_blocked: data.is_blocked,
      is_validate_ad: data.is_validate_ad,
      role_id: data.role_id,
    });
  };

  const footer = (
    <div className="flex justify-content-end gap-2">
      <Button
        label="Cancel"
        icon="pi pi-times"
        severity="secondary"
        outlined
        onClick={onHide}
      />
      <Button
        label="Save"
        icon="pi pi-check"
        loading={loading}
        onClick={handleSubmit(handleFormSubmit)}
      />
    </div>
  );

  return (
    <Dialog
      header={`Edit User: ${user?.username || ''}`}
      visible={visible}
      onHide={onHide}
      style={{ width: '450px' }}
      footer={footer}
      modal
      aria-label="Edit user dialog"
    >
      <form className="flex flex-column gap-4 pt-3">
        {/* Username (read-only) */}
        <div className="flex flex-column gap-2">
          <label className="font-medium">Username</label>
          <span className="text-900 font-semibold">{user?.username}</span>
        </div>

        {/* Role Assignment */}
        <div className="flex flex-column gap-2">
          <label htmlFor="edit-role" className="font-medium">Role</label>
          <Controller
            name="role_id"
            control={control}
            render={({ field }) => (
              <Dropdown
                id="edit-role"
                value={field.value}
                options={roleOptions}
                onChange={(e) => field.onChange(e.value)}
                placeholder={rolesLoading || loadingUserRole ? 'Loading...' : 'Select a role'}
                disabled={rolesLoading || loadingUserRole}
                className="w-full"
                aria-label="Assign role"
              />
            )}
          />
        </div>

        {/* Active */}
        <div className="flex align-items-center gap-3">
          <Controller
            name="is_active"
            control={control}
            render={({ field }) => (
              <InputSwitch
                id="edit-active"
                checked={field.value}
                onChange={(e) => field.onChange(e.value)}
                aria-label="Active status"
              />
            )}
          />
          <label htmlFor="edit-active" className="font-medium cursor-pointer">Active</label>
        </div>

        {/* Blocked */}
        <div className="flex align-items-center gap-3">
          <Controller
            name="is_blocked"
            control={control}
            render={({ field }) => (
              <InputSwitch
                id="edit-blocked"
                checked={field.value}
                onChange={(e) => field.onChange(e.value)}
                aria-label="Blocked status"
              />
            )}
          />
          <label htmlFor="edit-blocked" className="font-medium cursor-pointer">Blocked</label>
        </div>

        {/* Validate with AD */}
        <div className="flex align-items-center gap-3">
          <Controller
            name="is_validate_ad"
            control={control}
            render={({ field }) => (
              <InputSwitch
                id="edit-validate-ad"
                checked={field.value}
                onChange={(e) => field.onChange(e.value)}
                aria-label="Validate with AD"
              />
            )}
          />
          <label htmlFor="edit-validate-ad" className="font-medium cursor-pointer">
            Validate with AD
          </label>
        </div>
      </form>
    </Dialog>
  );
};
