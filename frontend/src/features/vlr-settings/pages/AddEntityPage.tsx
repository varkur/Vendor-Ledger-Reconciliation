/**
 * Add Another Entity page — Form to create a new company entity.
 * Fields: Country (dropdown), Entity Type (dropdown), Entity Name, Entity PAN
 * Actions: Create, Reset
 */

import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { InputText } from 'primereact/inputtext';
import { Dropdown } from 'primereact/dropdown';
import { Button } from 'primereact/button';
import { Toast } from 'primereact/toast';
import { apiClient } from '@shared/services/apiClient';
import { useAppDispatch } from '@app/store';
import { fetchEntities } from '@app/store/entitySlice';

const COUNTRY_OPTIONS = [
  { label: 'India', value: 'India' },
  { label: 'United States', value: 'United States' },
  { label: 'United Kingdom', value: 'United Kingdom' },
  { label: 'Singapore', value: 'Singapore' },
  { label: 'UAE', value: 'UAE' },
];

const ENTITY_TYPE_OPTIONS = [
  { label: 'Public company', value: 'Public company' },
  { label: 'Private company', value: 'Private company' },
  { label: 'LLP', value: 'LLP' },
  { label: 'Partnership', value: 'Partnership' },
  { label: 'Sole Proprietorship', value: 'Sole Proprietorship' },
];

export const AddEntityPage = () => {
  const toast = useRef<Toast>(null);
  const navigate = useNavigate();
  const dispatch = useAppDispatch();

  const [country, setCountry] = useState<string | null>(null);
  const [entityType, setEntityType] = useState<string | null>(null);
  const [entityName, setEntityName] = useState('');
  const [entityPan, setEntityPan] = useState('');
  const [companyCode, setCompanyCode] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleReset = () => {
    setCountry(null);
    setEntityType(null);
    setEntityName('');
    setEntityPan('');
    setCompanyCode('');
  };

  const handleCreate = async () => {
    if (!country || !entityType || !entityName.trim() || !entityPan.trim() || !companyCode.trim()) {
      toast.current?.show({
        severity: 'warn',
        summary: 'Validation',
        detail: 'All fields marked with * are required.',
      });
      return;
    }

    setIsSubmitting(true);
    try {
      await apiClient.post('/vlr/settings/entities', {
        country,
        entity_type: entityType,
        name: entityName.trim(),
        pan_card: entityPan.trim().toUpperCase(),
        company_code: companyCode.trim().toUpperCase(),
      });

      toast.current?.show({
        severity: 'success',
        summary: 'Entity Created',
        detail: `${entityName} has been added successfully.`,
      });

      // Refresh entity list in the topbar
      dispatch(fetchEntities());

      // Navigate back to company profile after a brief delay
      setTimeout(() => navigate('/settings/company-profile'), 1000);
    } catch (err: any) {
      toast.current?.show({
        severity: 'error',
        summary: 'Create Failed',
        detail: err.response?.data?.detail || 'Failed to create entity.',
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div>
      <Toast ref={toast} />

      {/* Page Header */}
      <div className="em-page-header">
        <h2>Add Another Entity</h2>
      </div>

      <div className="em-card" style={{ maxWidth: 800 }}>
        <div className="flex flex-column gap-4" style={{ padding: '1.5rem' }}>
          {/* Country */}
          <div className="flex align-items-center gap-3">
            <label
              htmlFor="entity-country"
              className="font-bold text-sm text-right"
              style={{ width: 140, flexShrink: 0 }}
            >
              Country <span style={{ color: 'var(--color-error, red)' }}>*</span>
            </label>
            <Dropdown
              id="entity-country"
              value={country}
              options={COUNTRY_OPTIONS}
              onChange={(e) => setCountry(e.value)}
              placeholder="Select Country"
              className="flex-1"
              style={{ minWidth: 300 }}
            />
          </div>

          {/* Entity Type */}
          <div className="flex align-items-center gap-3">
            <label
              htmlFor="entity-type"
              className="font-bold text-sm text-right"
              style={{ width: 140, flexShrink: 0 }}
            >
              Entity type <span style={{ color: 'var(--color-error, red)' }}>*</span>
            </label>
            <Dropdown
              id="entity-type"
              value={entityType}
              options={ENTITY_TYPE_OPTIONS}
              onChange={(e) => setEntityType(e.value)}
              placeholder="Select Entity Type"
              className="flex-1"
              style={{ minWidth: 300 }}
            />
          </div>

          {/* Entity Name */}
          <div className="flex align-items-center gap-3">
            <label
              htmlFor="entity-name"
              className="font-bold text-sm text-right"
              style={{ width: 140, flexShrink: 0 }}
            >
              Entity Name <span style={{ color: 'var(--color-error, red)' }}>*</span>
            </label>
            <InputText
              id="entity-name"
              value={entityName}
              onChange={(e) => setEntityName(e.target.value)}
              placeholder="Entity Name"
              className="flex-1"
              style={{ minWidth: 300 }}
            />
          </div>

          {/* Entity PAN */}
          <div className="flex align-items-center gap-3">
            <label
              htmlFor="entity-pan"
              className="font-bold text-sm text-right"
              style={{ width: 140, flexShrink: 0 }}
            >
              Entity PAN <span style={{ color: 'var(--color-error, red)' }}>*</span>
            </label>
            <InputText
              id="entity-pan"
              value={entityPan}
              onChange={(e) => setEntityPan(e.target.value)}
              placeholder="PAN"
              className="flex-1"
              style={{ minWidth: 300, textTransform: 'uppercase' }}
            />
          </div>

          {/* Company Code */}
          <div className="flex align-items-center gap-3">
            <label
              htmlFor="entity-code"
              className="font-bold text-sm text-right"
              style={{ width: 140, flexShrink: 0 }}
            >
              Company Code <span style={{ color: 'var(--color-error, red)' }}>*</span>
            </label>
            <div className="flex-1" style={{ minWidth: 300 }}>
              <InputText
                id="entity-code"
                value={companyCode}
                onChange={(e) => setCompanyCode(e.target.value.toUpperCase())}
                placeholder="e.g. EPL, GBL, ZHL, EBL"
                className="w-full"
                style={{ textTransform: 'uppercase' }}
              />
              <small className="block mt-1" style={{ color: 'var(--color-text-muted)' }}>
                Used as the prefix for request IDs (e.g. EPL-00094).
              </small>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex justify-content-end gap-2 mt-3">
            <Button
              label="Create"
              icon="pi pi-check"
              onClick={handleCreate}
              loading={isSubmitting}
              disabled={!country || !entityType || !entityName.trim() || !entityPan.trim() || !companyCode.trim()}
            />
            <Button
              label="Reset"
              className="p-button-outlined"
              onClick={handleReset}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
