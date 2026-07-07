/**
 * Add Party Dialog — form to create a new vendor/customer.
 * Uses react-hook-form + zod for validation.
 */

import { useEffect } from 'react';
import { Dialog } from 'primereact/dialog';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { Dropdown } from 'primereact/dropdown';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useCreateVendor } from '../hooks/useVendors';

const addPartySchema = z.object({
  partyType: z.enum(['Vendor', 'Customer']),
  partyCode: z.string().min(1, 'Party Code is required'),
  partyName: z.string().min(1, 'Party Name is required'),
  status: z.enum(['Active', 'Inactive']),
  pan: z.string().optional(),
  gstin: z.string().optional(),
  city: z.string().optional(),
  contactName: z.string().min(1, 'Contact Name is required'),
  contactEmail: z.string().min(1, 'Contact Email is required').email('Invalid email address'),
  contactMobile: z.string().optional(),
});

type AddPartyFormData = z.infer<typeof addPartySchema>;

const PARTY_TYPE_OPTIONS = [
  { label: 'Vendor', value: 'Vendor' },
  { label: 'Customer', value: 'Customer' },
];

const STATUS_OPTIONS = [
  { label: 'Active', value: 'Active' },
  { label: 'Inactive', value: 'Inactive' },
];

const DEFAULT_COMPANY_CODE = '1000';

interface AddPartyDialogProps {
  visible: boolean;
  onHide: () => void;
}

export const AddPartyDialog = ({ visible, onHide }: AddPartyDialogProps) => {
  const createVendor = useCreateVendor();

  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<AddPartyFormData>({
    resolver: zodResolver(addPartySchema),
    defaultValues: {
      partyType: 'Vendor',
      partyCode: '',
      partyName: '',
      status: 'Active',
      pan: '',
      gstin: '',
      city: '',
      contactName: '',
      contactEmail: '',
      contactMobile: '',
    },
  });

  useEffect(() => {
    if (!visible) {
      reset();
    }
  }, [visible, reset]);

  const onSubmit = (data: AddPartyFormData) => {
    createVendor.mutate(
      {
        vendor_code: data.partyCode,
        company_code: DEFAULT_COMPANY_CODE,
        name: data.partyName,
        pan: data.pan || undefined,
        gstin: data.gstin || undefined,
        city: data.city || undefined,
        status: data.status,
        contacts: [
          {
            name: data.contactName,
            email: data.contactEmail,
            phone: data.contactMobile || undefined,
          },
        ],
      },
      {
        onSuccess: () => {
          onHide();
        },
      }
    );
  };

  const dialogFooter = (
    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
      <Button
        label="Cancel"
        icon="pi pi-times"
        className="p-button-text"
        onClick={onHide}
        disabled={createVendor.isPending}
      />
      <Button
        label="Save"
        icon="pi pi-check"
        onClick={handleSubmit(onSubmit)}
        loading={createVendor.isPending}
      />
    </div>
  );

  return (
    <Dialog
      header="Add Party"
      visible={visible}
      onHide={onHide}
      style={{ width: '550px' }}
      footer={dialogFooter}
      modal
      closable
      draggable={false}
    >
      <form onSubmit={handleSubmit(onSubmit)} className="p-fluid">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          {/* Party Type */}
          <div className="field">
            <label htmlFor="partyType">Party Type</label>
            <Controller
              name="partyType"
              control={control}
              render={({ field }) => (
                <Dropdown
                  id="partyType"
                  {...field}
                  options={PARTY_TYPE_OPTIONS}
                  placeholder="Select Type"
                />
              )}
            />
          </div>

          {/* Status */}
          <div className="field">
            <label htmlFor="status">Status</label>
            <Controller
              name="status"
              control={control}
              render={({ field }) => (
                <Dropdown
                  id="status"
                  {...field}
                  options={STATUS_OPTIONS}
                  placeholder="Select Status"
                />
              )}
            />
          </div>

          {/* Party Code */}
          <div className="field">
            <label htmlFor="partyCode">Party Code *</label>
            <Controller
              name="partyCode"
              control={control}
              render={({ field }) => (
                <InputText
                  id="partyCode"
                  {...field}
                  className={errors.partyCode ? 'p-invalid' : ''}
                  placeholder="Enter party code"
                />
              )}
            />
            {errors.partyCode && (
              <small className="p-error">{errors.partyCode.message}</small>
            )}
          </div>

          {/* Party Name */}
          <div className="field">
            <label htmlFor="partyName">Party Name *</label>
            <Controller
              name="partyName"
              control={control}
              render={({ field }) => (
                <InputText
                  id="partyName"
                  {...field}
                  className={errors.partyName ? 'p-invalid' : ''}
                  placeholder="Enter party name"
                />
              )}
            />
            {errors.partyName && (
              <small className="p-error">{errors.partyName.message}</small>
            )}
          </div>

          {/* PAN */}
          <div className="field">
            <label htmlFor="pan">PAN</label>
            <Controller
              name="pan"
              control={control}
              render={({ field }) => (
                <InputText id="pan" {...field} value={field.value ?? ''} placeholder="Enter PAN" />
              )}
            />
          </div>

          {/* GSTIN */}
          <div className="field">
            <label htmlFor="gstin">GSTIN</label>
            <Controller
              name="gstin"
              control={control}
              render={({ field }) => (
                <InputText id="gstin" {...field} value={field.value ?? ''} placeholder="Enter GSTIN" />
              )}
            />
          </div>

          {/* City */}
          <div className="field" style={{ gridColumn: 'span 2' }}>
            <label htmlFor="city">City</label>
            <Controller
              name="city"
              control={control}
              render={({ field }) => (
                <InputText id="city" {...field} value={field.value ?? ''} placeholder="Enter city" />
              )}
            />
          </div>
        </div>

        {/* Contact Section */}
        <h4 style={{ marginTop: '1.5rem', marginBottom: '0.75rem' }}>Primary Contact</h4>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          {/* Contact Name */}
          <div className="field">
            <label htmlFor="contactName">Contact Name *</label>
            <Controller
              name="contactName"
              control={control}
              render={({ field }) => (
                <InputText
                  id="contactName"
                  {...field}
                  className={errors.contactName ? 'p-invalid' : ''}
                  placeholder="Enter contact name"
                />
              )}
            />
            {errors.contactName && (
              <small className="p-error">{errors.contactName.message}</small>
            )}
          </div>

          {/* Contact Email */}
          <div className="field">
            <label htmlFor="contactEmail">Contact Email *</label>
            <Controller
              name="contactEmail"
              control={control}
              render={({ field }) => (
                <InputText
                  id="contactEmail"
                  {...field}
                  className={errors.contactEmail ? 'p-invalid' : ''}
                  placeholder="Enter contact email"
                />
              )}
            />
            {errors.contactEmail && (
              <small className="p-error">{errors.contactEmail.message}</small>
            )}
          </div>

          {/* Contact Mobile */}
          <div className="field" style={{ gridColumn: 'span 2' }}>
            <label htmlFor="contactMobile">Contact Mobile</label>
            <Controller
              name="contactMobile"
              control={control}
              render={({ field }) => (
                <InputText id="contactMobile" {...field} value={field.value ?? ''} placeholder="Enter mobile number" />
              )}
            />
          </div>
        </div>

        {/* Error display */}
        {createVendor.isError && (
          <div style={{ marginTop: '1rem' }}>
            <small className="p-error">
              {createVendor.error instanceof Error
                ? createVendor.error.message
                : 'Failed to create party. Please try again.'}
            </small>
          </div>
        )}
      </form>
    </Dialog>
  );
};
