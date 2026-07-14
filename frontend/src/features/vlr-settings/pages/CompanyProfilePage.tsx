/**
 * Company Profile page — Entity-level settings for letterhead, logo, and contact info.
 * Matches the Firmway Company Profile layout.
 *
 * Fields:
 * - Entity Name (read-only, with Verified badge)
 * - Entity Type (read-only)
 * - Entity PAN Card (read-only)
 * - Entity Email (editable)
 * - Letterhead Header (file select, max 770x150)
 * - Letterhead Footer (file select, max 770x120)
 * - Website address
 * - Telephone number
 * - Registered Office Address (textarea)
 * - Company Logo (file select, max 770x120)
 * - Company Code
 */

import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { Button } from 'primereact/button';
import { Toast } from 'primereact/toast';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';
import { Badge } from 'primereact/badge';

import { useCompanyProfile, useUpdateCompanyProfile } from '../hooks/useCompanyProfile';

export const CompanyProfilePage = () => {
  const toast = useRef<Toast>(null);
  const navigate = useNavigate();

  const { data: profile, isLoading, isError, error, refetch } = useCompanyProfile();
  const updateMutation = useUpdateCompanyProfile();

  // Editable fields
  const [email, setEmail] = useState('');
  const [website, setWebsite] = useState('');
  const [telephone, setTelephone] = useState('');
  const [registeredAddress, setRegisteredAddress] = useState('');
  const [companyCode, setCompanyCode] = useState('');
  const [letterheadHeader, setLetterheadHeader] = useState('');
  const [letterheadFooter, setLetterheadFooter] = useState('');
  const [logo, setLogo] = useState('');

  useEffect(() => {
    if (profile) {
      setEmail(profile.email);
      setWebsite(profile.website);
      setTelephone(profile.telephone);
      setRegisteredAddress(profile.registered_address);
      setCompanyCode(profile.company_code);
      setLetterheadHeader(profile.letterhead_header);
      setLetterheadFooter(profile.letterhead_footer);
      setLogo(profile.logo);
    }
  }, [profile]);

  const handleUpdate = () => {
    updateMutation.mutate(
      {
        email,
        website,
        telephone,
        registered_address: registeredAddress,
        company_code: companyCode,
        letterhead_header: letterheadHeader,
        letterhead_footer: letterheadFooter,
        logo,
      },
      {
        onSuccess: () => {
          toast.current?.show({
            severity: 'success',
            summary: 'Profile Updated',
            detail: 'Company profile has been saved successfully.',
          });
        },
        onError: (err) => {
          toast.current?.show({
            severity: 'error',
            summary: 'Update Failed',
            detail: err.message || 'Failed to update company profile.',
          });
        },
      }
    );
  };

  const handleCancel = () => {
    if (profile) {
      setEmail(profile.email);
      setWebsite(profile.website);
      setTelephone(profile.telephone);
      setRegisteredAddress(profile.registered_address);
      setCompanyCode(profile.company_code);
      setLetterheadHeader(profile.letterhead_header);
      setLetterheadFooter(profile.letterhead_footer);
      setLogo(profile.logo);
    }
  };

  if (isLoading) {
    return (
      <div className="flex justify-content-center align-items-center" style={{ minHeight: 300 }}>
        <ProgressSpinner style={{ width: '50px', height: '50px' }} />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-column align-items-center gap-3" style={{ padding: '2rem' }}>
        <Message severity="error" text={error?.message || 'Failed to load company profile.'} />
        <Button label="Retry" icon="pi pi-refresh" onClick={() => refetch()} />
      </div>
    );
  }

  return (
    <div>
      <Toast ref={toast} />

      {/* Page Header */}
      <div className="em-page-header">
        <h2>Company Profile</h2>
      </div>

      <div className="em-card">
        {/* Row 1: Entity Name + Entity Type */}
        <div className="grid mb-4">
          <div className="col-12 md:col-6">
            <div className="flex align-items-center gap-2 mb-1">
              <label className="font-bold text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                Entity Name
              </label>
            </div>
            <div className="flex align-items-center gap-2">
              <span className="text-lg font-semibold">{profile?.entity_name || '—'}</span>
              {profile?.verified && (
                <Badge value="Verified" severity="success" />
              )}
            </div>
          </div>
          <div className="col-12 md:col-6">
            <label className="font-bold text-sm block mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              Entity Type
            </label>
            <span className="text-lg">{profile?.entity_type || '—'}</span>
          </div>
        </div>

        {/* Row 2: Entity PAN Card + Entity Email */}
        <div className="grid mb-4">
          <div className="col-12 md:col-6">
            <label className="font-bold text-sm block mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              Entity PAN Card
            </label>
            <span className="text-lg font-mono">{profile?.pan_card || '—'}</span>
          </div>
          <div className="col-12 md:col-6">
            <label htmlFor="cp-email" className="font-bold text-sm block mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              Entity Email
            </label>
            <InputText
              id="cp-email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Company Email"
              className="w-full"
            />
          </div>
        </div>

        {/* Letterhead section header */}
        <div className="mb-3">
          <p className="text-sm" style={{ color: 'var(--color-text-muted)', fontStyle: 'italic' }}>
            For letter head purpose kindly fill in
          </p>
        </div>

        {/* Row 3: Letterhead Header + Letterhead Footer */}
        <div className="grid mb-4">
          <div className="col-12 md:col-6">
            <label htmlFor="cp-header" className="font-bold text-sm block mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              Letterhead Header (max width:770px, max height: 150px)
            </label>
            <div className="p-inputgroup">
              <InputText
                id="cp-header"
                value={letterheadHeader}
                onChange={(e) => setLetterheadHeader(e.target.value)}
                placeholder="Select Entity Header"
                className="w-full"
              />
              <Button icon="pi pi-upload" className="p-button-outlined" aria-label="Upload header" />
            </div>
          </div>
          <div className="col-12 md:col-6">
            <label htmlFor="cp-footer" className="font-bold text-sm block mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              Letterhead Footer (max width:770px, max height: 120px)
            </label>
            <div className="p-inputgroup">
              <InputText
                id="cp-footer"
                value={letterheadFooter}
                onChange={(e) => setLetterheadFooter(e.target.value)}
                placeholder="Select Entity Footer"
                className="w-full"
              />
              <Button icon="pi pi-upload" className="p-button-outlined" aria-label="Upload footer" />
            </div>
          </div>
        </div>

        {/* Row 4: Website + Telephone */}
        <div className="grid mb-4">
          <div className="col-12 md:col-6">
            <label htmlFor="cp-website" className="font-bold text-sm block mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              Website address
            </label>
            <InputText
              id="cp-website"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              placeholder="https://emcure.com"
              className="w-full"
            />
          </div>
          <div className="col-12 md:col-6">
            <label htmlFor="cp-telephone" className="font-bold text-sm block mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              Telephone number
            </label>
            <InputText
              id="cp-telephone"
              value={telephone}
              onChange={(e) => setTelephone(e.target.value)}
              placeholder="Company Contact Number"
              className="w-full"
            />
          </div>
        </div>

        {/* Row 5: Registered Address + Logo + Company Code */}
        <div className="grid mb-4">
          <div className="col-12 md:col-6">
            <label htmlFor="cp-address" className="font-bold text-sm block mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              Registered Office Address
            </label>
            <InputTextarea
              id="cp-address"
              value={registeredAddress}
              onChange={(e) => setRegisteredAddress(e.target.value)}
              placeholder="Registered Address"
              rows={4}
              className="w-full"
              autoResize
            />
          </div>
          <div className="col-12 md:col-6">
            <div className="mb-3">
              <label htmlFor="cp-logo" className="font-bold text-sm block mb-1" style={{ color: 'var(--color-text-secondary)' }}>
                Company Logo (max width:770px, max height: 120px)
              </label>
              <div className="p-inputgroup">
                <InputText
                  id="cp-logo"
                  value={logo}
                  onChange={(e) => setLogo(e.target.value)}
                  placeholder="Select Entity Logo"
                  className="w-full"
                />
                <Button icon="pi pi-upload" className="p-button-outlined" aria-label="Upload logo" />
              </div>
            </div>
            <div>
              <label htmlFor="cp-code" className="font-bold text-sm block mb-1" style={{ color: 'var(--color-text-secondary)' }}>
                Company Code
              </label>
              <InputText
                id="cp-code"
                value={companyCode}
                onChange={(e) => setCompanyCode(e.target.value)}
                placeholder="Company Code"
                className="w-full"
              />
            </div>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex justify-content-end gap-2 pt-3 border-top-1 surface-border">
          <Button
            label="Cancel"
            className="p-button-text"
            onClick={handleCancel}
          />
          <Button
            label="Update"
            icon="pi pi-check"
            onClick={handleUpdate}
            loading={updateMutation.isPending}
          />
        </div>
      </div>

      {/* Add Entity / Add Division buttons */}
      <div className="flex gap-3 mt-4">
        <Button
          label="Add another Entity"
          icon="pi pi-plus"
          className="p-button-danger"
          onClick={() => navigate('/settings/add-entity')}
        />
        <Button
          label="Add Division"
          icon="pi pi-plus"
          className="p-button-outlined"
          onClick={() => {
            toast.current?.show({
              severity: 'info',
              summary: 'Add Division',
              detail: 'Add Division form will open here.',
            });
          }}
        />
      </div>
    </div>
  );
};
