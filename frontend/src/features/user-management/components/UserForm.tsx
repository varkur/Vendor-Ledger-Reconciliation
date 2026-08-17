/**
 * User create form component.
 * Includes single role assignment via Dropdown.
 */

import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { InputText } from 'primereact/inputtext';
import { Password } from 'primereact/password';
import { Dropdown } from 'primereact/dropdown';
import { InputSwitch } from 'primereact/inputswitch';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { useRoles } from '../hooks/useRoles';
import type { CreateUserRequest } from '../models/User';

const createUserSchema = z.object({
  username: z.string().min(3, 'Username must be at least 3 characters').max(255),
  password: z
    .string()
    .max(128)
    .refine((val) => val.length === 0 || val.length >= 8, {
      message: 'Password must be at least 8 characters',
    })
    .optional()
    .or(z.literal('')),
  is_validate_ad: z.boolean(),
  role_id: z.string().min(1, 'Role is required'),
  name: z.string().min(1, 'Name is required').max(255),
  email: z.string().email('Enter a valid email address'),
  department: z.string().min(1, 'Department is required').max(255),
  designation_title: z.string().max(255).optional(),
  reporting_manager: z.string().max(255).optional(),
  employee_id: z.string().max(50).optional(),
});

type CreateUserFormData = z.infer<typeof createUserSchema>;

interface UserFormProps {
  visible: boolean;
  onHide: () => void;
  onSubmit: (data: CreateUserRequest) => void;
  loading?: boolean;
}

export const UserForm = ({ visible, onHide, onSubmit, loading }: UserFormProps) => {
  const { roleOptions, loading: rolesLoading } = useRoles();

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors },
  } = useForm<CreateUserFormData>({
    resolver: zodResolver(createUserSchema),
    defaultValues: {
      is_validate_ad: true,
      role_id: '',
      name: '',
      email: '',
      department: '',
      designation_title: '',
      reporting_manager: '',
      employee_id: '',
    },
  });

  const handleFormSubmit = (data: CreateUserFormData) => {
    onSubmit({
      ...data,
      password: data.password ? data.password : null,
      employee_id: data.employee_id || null,
    });
    reset();
  };

  const footer = (
    <div className="flex justify-content-end gap-2">
      <Button
        label="Cancel"
        icon="pi pi-times"
        severity="secondary"
        outlined
        onClick={() => { reset(); onHide(); }}
      />
      <Button
        label="Create"
        icon="pi pi-check"
        loading={loading}
        onClick={handleSubmit(handleFormSubmit)}
      />
    </div>
  );

  return (
    <Dialog
      header="Create New User"
      visible={visible}
      onHide={() => { reset(); onHide(); }}
      style={{ width: '450px' }}
      footer={footer}
      modal
      aria-label="Create user dialog"
    >
      <form className="flex flex-column gap-4 pt-3">
        <div className="flex flex-column gap-2">
          <label htmlFor="new-username" className="font-medium">Username</label>
          <InputText
            id="new-username"
            {...register('username')}
            placeholder="Enter username"
            className={errors.username ? 'p-invalid' : ''}
            aria-describedby="new-username-error"
          />
          {errors.username && (
            <small id="new-username-error" className="p-error">{errors.username.message}</small>
          )}
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="new-name" className="font-medium">Full Name</label>
          <InputText
            id="new-name"
            {...register('name')}
            placeholder="Enter full name"
            className={errors.name ? 'p-invalid' : ''}
            aria-describedby="new-name-error"
          />
          {errors.name && (
            <small id="new-name-error" className="p-error">{errors.name.message}</small>
          )}
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="new-email" className="font-medium">Email</label>
          <InputText
            id="new-email"
            {...register('email')}
            placeholder="Enter email address"
            className={errors.email ? 'p-invalid' : ''}
            aria-describedby="new-email-error"
          />
          {errors.email && (
            <small id="new-email-error" className="p-error">{errors.email.message}</small>
          )}
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="new-department" className="font-medium">Department</label>
          <InputText
            id="new-department"
            {...register('department')}
            placeholder="Enter department"
            className={errors.department ? 'p-invalid' : ''}
            aria-describedby="new-department-error"
          />
          {errors.department && (
            <small id="new-department-error" className="p-error">{errors.department.message}</small>
          )}
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="new-designation" className="font-medium">Designation (optional)</label>
          <InputText
            id="new-designation"
            {...register('designation_title')}
            placeholder="Enter designation"
          />
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="new-reporting-manager" className="font-medium">Reporting Manager (optional)</label>
          <InputText
            id="new-reporting-manager"
            {...register('reporting_manager')}
            placeholder="Enter reporting manager"
          />
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="new-employee-id" className="font-medium">Employee ID (optional)</label>
          <InputText
            id="new-employee-id"
            {...register('employee_id')}
            placeholder="Defaults to username when omitted"
          />
        </div>

        <div className="flex flex-column gap-2">
          <label htmlFor="new-password" className="font-medium">Password (optional)</label>
          <Controller
            name="password"
            control={control}
            render={({ field }) => (
              <Password
                id="new-password"
                {...field}
                placeholder="Leave blank to use default password"
                toggleMask
                className={errors.password ? 'p-invalid' : ''}
                inputClassName="w-full"
                aria-describedby="new-password-error"
              />
            )}
          />
          {errors.password && (
            <small id="new-password-error" className="p-error">{errors.password.message}</small>
          )}
        </div>

        {/* Role Assignment */}
        <div className="flex flex-column gap-2">
          <label htmlFor="new-role" className="font-medium">Role</label>
          <Controller
            name="role_id"
            control={control}
            render={({ field }) => (
              <Dropdown
                id="new-role"
                value={field.value}
                options={roleOptions}
                onChange={(e) => field.onChange(e.value)}
                placeholder={rolesLoading ? 'Loading roles...' : 'Select a role'}
                disabled={rolesLoading}
                className={`w-full ${errors.role_id ? 'p-invalid' : ''}`}
                aria-label="Assign role"
              />
            )}
          />
          {errors.role_id && (
            <small className="p-error">{errors.role_id.message}</small>
          )}
        </div>

        <div className="flex align-items-center gap-3">
          <Controller
            name="is_validate_ad"
            control={control}
            render={({ field }) => (
              <InputSwitch
                id="new-validate-ad"
                checked={field.value}
                onChange={(e) => field.onChange(e.value)}
                aria-label="Validate with AD"
              />
            )}
          />
          <label htmlFor="new-validate-ad" className="font-medium cursor-pointer">
            Validate with AD
          </label>
        </div>
      </form>
    </Dialog>
  );
};
