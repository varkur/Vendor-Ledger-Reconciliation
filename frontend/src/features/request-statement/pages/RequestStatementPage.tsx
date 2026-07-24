/**
 * Request Statement page — Multi-step form for creating a new party request.
 * Step 1: Configure (sender settings, responder settings, reconciliation settings, email settings)
 * Step 2: Upload Statement
 *
 * Wired to backend APIs:
 * - POST /api/v1/vlr/requests (create reconciliation request with vendor_ids)
 * - GET /api/v1/vlr/vendors (fetch vendor list for selection)
 * - GET /api/v1/vlr/settings/email-config (fetch email sender configuration)
 * - GET /api/v1/vlr/vendors/{vendor_id}/contacts (fetch vendor contacts)
 * - GET /api/v1/vlr/email-templates/{id}/preview (fetch email template preview)
 *
 * Implements loading indicators, error handling, and form validation.
 *
 * Requirements: 9, 10, 23.3, 25.1, 25.2
 */

import { useState, useCallback, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { InputText } from 'primereact/inputtext';
import { Dropdown } from 'primereact/dropdown';
import { RadioButton } from 'primereact/radiobutton';
import { Calendar } from 'primereact/calendar';
import { InputTextarea } from 'primereact/inputtextarea';
import { Button } from 'primereact/button';
import { MultiSelect } from 'primereact/multiselect';
import { Message } from 'primereact/message';
import { ProgressSpinner } from 'primereact/progressspinner';
import { ProgressBar } from 'primereact/progressbar';
import { Dialog } from 'primereact/dialog';
import { Toast } from 'primereact/toast';
import { FileUpload, FileUploadHandlerEvent } from 'primereact/fileupload';

import { useVendorSelection, useCreateStatementRequest, useUploadCompanyLedger } from '../hooks/useRequestStatement';
import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@shared/services/apiClient';

type Step = 'configure' | 'upload';

const DEFAULT_FISCAL_YEAR = '2024-25';

/** Response from the email-config endpoint */
interface EmailConfigResponse {
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  sender_email: string;
  sender_name: string;
  use_tls: boolean;
  is_configured: boolean;
}

/** Vendor contact from the contacts endpoint */
interface VendorContact {
  id: string;
  name: string;
  email: string;
  phone?: string;
  designation?: string;
  is_primary?: boolean;
}

export const RequestStatementPage = () => {
  const { companyCode } = useSelectedEntity();
  const toast = useRef<Toast>(null);
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState<Step>('configure');
  const [title, setTitle] = useState('');
  const [requestType, setRequestType] = useState('Ledger');
  const [uploadShareOption, setUploadShareOption] = useState('Upload Statement (Do Not Share)');
  const [importVia, setImportVia] = useState('');
  const [template, setTemplate] = useState('Positive');
  const [startDate, setStartDate] = useState<Date | null>(null);
  const [endDate, setEndDate] = useState<Date | null>(null);
  const [branch, setBranch] = useState('All');
  const [remarks, setRemarks] = useState('');
  const [selectedVendorIds, setSelectedVendorIds] = useState<string[]>([]);
  const [vendorSearch, setVendorSearch] = useState('');

  // Responder settings
  const [requestOpenItem, setRequestOpenItem] = useState('No');
  const [requestLedger, setRequestLedger] = useState('Yes');
  const [allowDateChange, setAllowDateChange] = useState('No');
  const [fileFormat, setFileFormat] = useState('Excel Only');

  // Reconciliation settings
  const [amountTolerance, setAmountTolerance] = useState('1');
  const [dateRangeMin, setDateRangeMin] = useState('0');
  const [dateRangeMax, setDateRangeMax] = useState('15');
  const [tdsMin, setTdsMin] = useState('0');
  const [tdsMax, setTdsMax] = useState('10');
  const [gstPercentage, setGstPercentage] = useState('18');
  const [carryForward, setCarryForward] = useState('Yes');

  // Email settings
  const [sendEmailFrom, setSendEmailFrom] = useState('');
  const [emailTemplate, setEmailTemplate] = useState('');
  const [reminderTemplate, setReminderTemplate] = useState('');
  const [contactPerson, setContactPerson] = useState('');
  const [emailAttachment, setEmailAttachment] = useState('company_ledger');
  const [sendNow, setSendNow] = useState('Now');

  // Preview dialog state
  const [previewVisible, setPreviewVisible] = useState(false);
  const [previewHtml, setPreviewHtml] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState('');

  // Success state
  const [showSuccess, setShowSuccess] = useState(false);
  const [inviteSent, setInviteSent] = useState(false);
  const [isSendingInvites, setIsSendingInvites] = useState(false);

  // Validation errors
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  // ─── API Hooks ───────────────────────────────────────────────────────────────
  const {
    data: vendorData,
    isLoading: isLoadingVendors,
    isError: isVendorError,
    error: vendorError,
    refetch: refetchVendors,
  } = useVendorSelection(companyCode, vendorSearch);

  const createMutation = useCreateStatementRequest();

  // Upload hook — enabled once request is created (request_id available)
  const requestId = createMutation.data?.id || '';
  const { mutateAsync: uploadFile, uploadProgress, isPending: isUploading } = useUploadCompanyLedger(requestId, companyCode);
  const [uploadComplete, setUploadComplete] = useState(false);

  // Fetch email templates for dropdowns
  const { data: emailTemplatesData } = useQuery<{ items: Array<{ id: string; name: string; subject: string; category: string }> }>({
    queryKey: ['email-templates', companyCode],
    queryFn: async () => {
      const { data } = await apiClient.get('/vlr/email-templates', {
        params: { company_code: companyCode, page_size: 50 },
      });
      return data;
    },
    enabled: !!companyCode,
    staleTime: 60_000,
  });

  // Fetch email config for "Send Email From" dropdown
  const {
    data: emailConfigData,
    isLoading: isLoadingEmailConfig,
  } = useQuery<EmailConfigResponse>({
    queryKey: ['email-config', companyCode],
    queryFn: async () => {
      const { data } = await apiClient.get('/vlr/settings/email-config', {
        params: { company_code: companyCode },
      });
      return data;
    },
    enabled: !!companyCode,
    staleTime: 60_000,
  });

  // Fetch vendor contacts for "Contact Person" dropdown (uses first selected vendor)
  const firstSelectedVendorId = selectedVendorIds.length > 0 ? selectedVendorIds[0] : '';
  const {
    data: vendorContactsData,
    isLoading: isLoadingContacts,
  } = useQuery<VendorContact[]>({
    queryKey: ['vendor-contacts', firstSelectedVendorId, companyCode],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/vendors/${firstSelectedVendorId}/contacts`, {
        params: { company_code: companyCode },
      });
      // Backend returns list[VendorContactResponse] directly (flat array)
      return Array.isArray(data) ? data : data.items ?? [];
    },
    enabled: !!firstSelectedVendorId && !!companyCode,
    staleTime: 30_000,
  });

  // ─── Derived Data ────────────────────────────────────────────────────────────
  const emailTemplateOptions = useMemo(() => {
    if (!emailTemplatesData?.items) return [];
    return emailTemplatesData.items
      .filter((t) => t.category === 'ledger_request' || t.category === 'general')
      .map((t) => ({ label: t.name, value: t.id }));
  }, [emailTemplatesData]);

  const reminderTemplateOptions = useMemo(() => {
    if (!emailTemplatesData?.items) return [];
    return emailTemplatesData.items
      .filter((t) => t.category === 'reminder' || t.category === 'escalation')
      .map((t) => ({ label: t.name, value: t.id }));
  }, [emailTemplatesData]);

  // "Send Email From" dropdown options from email config
  const sendEmailFromOptions = useMemo(() => {
    if (!emailConfigData || !emailConfigData.is_configured) {
      return [{ label: 'No email configured', value: '' }];
    }
    const label = emailConfigData.sender_name
      ? `${emailConfigData.sender_name} <${emailConfigData.sender_email}>`
      : emailConfigData.sender_email;
    return [{ label, value: emailConfigData.sender_email }];
  }, [emailConfigData]);

  // "Contact Person" dropdown options from vendor contacts
  const contactPersonOptions = useMemo(() => {
    if (!vendorContactsData || vendorContactsData.length === 0) {
      return [];
    }
    return vendorContactsData.map((c) => ({
      label: c.email ? `${c.name} (${c.email})` : c.name,
      value: c.id,
    }));
  }, [vendorContactsData]);

  // "Email Attachment" dropdown options
  const emailAttachmentOptions = useMemo(() => {
    return [
      { label: 'Company Ledger Extract', value: 'company_ledger' },
      { label: 'None', value: 'none' },
    ];
  }, []);

  const vendorOptions = useMemo(() => {
    if (!vendorData?.items) return [];
    return vendorData.items.map((v) => ({
      label: `${v.vendor_code} — ${v.name}`,
      value: v.id,
    }));
  }, [vendorData]);

  // ─── Dropdown Options ────────────────────────────────────────────────────────
  const requestTypeOptions = [
    { label: 'Ledger', value: 'Ledger' },
    { label: 'Balance Confirmation', value: 'Balance Confirmation' },
  ];

  const uploadShareOptions = [
    { label: 'Upload Statement (Do Not Share)', value: 'Upload Statement (Do Not Share)' },
    { label: 'Upload & Share Statement', value: 'Upload & Share Statement' },
  ];

  const importViaOptions = [
    { label: 'Select Browse File or SFTP', value: '' },
    { label: 'Browse File', value: 'Browse File' },
    { label: 'SFTP', value: 'SFTP' },
  ];

  const branchOptions = [
    { label: 'All', value: 'All' },
    { label: 'Pune', value: 'Pune' },
    { label: 'Mumbai', value: 'Mumbai' },
  ];

  const carryForwardOptions = [
    { label: 'Yes', value: 'Yes' },
    { label: 'No', value: 'No' },
  ];

  // ─── Form Validation ─────────────────────────────────────────────────────────
  const validateForm = useCallback((): boolean => {
    const errors: Record<string, string> = {};

    if (!title.trim()) {
      errors.title = 'Title is required';
    }
    if (!startDate) {
      errors.startDate = 'Start date is required';
    }
    if (!endDate) {
      errors.endDate = 'End date is required';
    }
    if (startDate && endDate && startDate >= endDate) {
      errors.endDate = 'End date must be after start date';
    }
    if (selectedVendorIds.length === 0) {
      errors.vendors = 'At least one vendor must be selected';
    }

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  }, [title, startDate, endDate, selectedVendorIds]);

  // ─── Handlers ────────────────────────────────────────────────────────────────
  const formatDateToISO = (d: Date | null): string => {
    if (!d) return '';
    const iso = d.toISOString();
    return iso.substring(0, iso.indexOf('T'));
  };

  const handleSubmit = useCallback(() => {
    if (!validateForm()) return;

    createMutation.mutate(
      {
        company_code: companyCode,
        fiscal_year: DEFAULT_FISCAL_YEAR,
        period_start: formatDateToISO(startDate),
        period_end: formatDateToISO(endDate),
        vendor_ids: selectedVendorIds,
        tolerance_amount: parseFloat(amountTolerance) || 0,
        tds_percentage: parseFloat(tdsMax) || 0,
        gst_percentage: parseFloat(gstPercentage) || 0,
      },
      {
        onSuccess: () => {
          setCurrentStep('upload');
        },
      }
    );
  }, [
    validateForm, createMutation, startDate, endDate,
    selectedVendorIds, amountTolerance, tdsMax, gstPercentage,
  ]);

  const handleVendorFilter = useCallback((e: { filter: string }) => {
    setVendorSearch(e.filter);
  }, []);

  const handleSelectAllVendors = useCallback(() => {
    if (selectedVendorIds.length > 0) {
      setSelectedVendorIds([]);
    } else {
      setSelectedVendorIds(vendorOptions.map((v) => v.value));
    }
  }, [vendorOptions, selectedVendorIds]);

  // Preview email template handler
  const handlePreview = useCallback(async () => {
    if (!emailTemplate) {
      toast.current?.show({
        severity: 'warn',
        summary: 'No Template Selected',
        detail: 'Please select an email template before previewing.',
      });
      return;
    }

    setPreviewVisible(true);
    setPreviewLoading(true);
    setPreviewError('');
    setPreviewHtml('');

    try {
      const { data } = await apiClient.get(`/vlr/email-templates/${emailTemplate}/preview`, {
        params: { company_code: companyCode },
      });
      // The preview endpoint may return { html: string } or a raw HTML string
      const html = typeof data === 'string' ? data : data.html || data.body || '';
      setPreviewHtml(html);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to load email preview.';
      setPreviewError(message);
    } finally {
      setPreviewLoading(false);
    }
  }, [emailTemplate, companyCode]);

  const handleResetSuccess = useCallback(() => {
    setShowSuccess(false);
    setTitle('');
    setSelectedVendorIds([]);
    setStartDate(null);
    setEndDate(null);
    setRemarks('');
    setCurrentStep('configure');
    setInviteSent(false);
    createMutation.reset();
  }, [createMutation]);

  const handleSendInvites = useCallback(async () => {
    if (!requestId) return;
    setIsSendingInvites(true);
    try {
      // Resolve the selected contact-person id to its email, sent as CC so the
      // chosen contact is copied alongside the vendor's primary contact.
      const selectedContact = (vendorContactsData || []).find(
        (c) => c.id === contactPerson
      );
      const ccEmails = selectedContact?.email ? [selectedContact.email] : [];

      const { data } = await apiClient.post(
        `/vlr/reconciliation-requests/${requestId}/send-vendor-invites`,
        { cc_emails: ccEmails },
        { params: { company_code: companyCode } }
      );
      setInviteSent(true);
      const sent = data.emails_sent || 0;
      const failed = data.emails_failed || 0;
      if (sent > 0) {
        setInviteSent(true);
        toast.current?.show({
          severity: 'success',
          summary: 'Invites Sent',
          detail: `${sent} vendor invite email(s) sent successfully.${failed > 0 ? ` ${failed} failed.` : ''}`,
          life: 5000,
        });
      } else {
        toast.current?.show({
          severity: 'warn',
          summary: 'No Emails Sent',
          detail: data.details?.[0]?.reason || 'No vendor contacts found. Please add contacts to your vendors first.',
          life: 8000,
        });
      }
    } catch (error: any) {
      const detail = error.response?.data?.detail || 'Failed to send vendor invites.';
      toast.current?.show({
        severity: 'error',
        summary: 'Send Failed',
        detail,
        life: 8000,
      });
    } finally {
      setIsSendingInvites(false);
    }
  }, [requestId, companyCode, contactPerson, vendorContactsData]);

  // ─── Main Render ────────────────────────────────────────────────────────────
  return (
    <div>
      <h2>New Party Request</h2>

      {/* Step Progress */}
      <div className="em-step-progress">
        <div
          className={`em-step ${currentStep === 'configure' ? 'active' : currentStep === 'upload' ? 'completed' : ''}`}
          onClick={() => setCurrentStep('configure')}
          style={{ cursor: 'pointer' }}
        >
          Configure
        </div>
        <div
          className={`em-step ${currentStep === 'upload' ? 'active' : ''}`}
          onClick={() => setCurrentStep('upload')}
          style={{ cursor: 'pointer' }}
        >
          Upload Statement
        </div>
      </div>

      {/* Mutation Error Banner */}
      {createMutation.isError && (
        <Message
          severity="error"
          text={
            createMutation.error?.message ??
            'Failed to create statement request. Please try again.'
          }
          className="w-full mb-3"
        />
      )}

      {currentStep === 'configure' && (
        <div>
          {/* Request Title */}
          <div className="em-form-section">
            <div className="em-form-section-title">Request Title</div>
            <div className="grid">
              <div className="col-12 md:col-6">
                <label className="block mb-2 font-medium text-sm">Title*</label>
                <InputText
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Eg. request for vendors"
                  className={`w-full ${validationErrors.title ? 'p-invalid' : ''}`}
                  aria-label="Request title"
                />
                {validationErrors.title && (
                  <small className="p-error">{validationErrors.title}</small>
                )}
              </div>
            </div>
          </div>

          {/* Vendor Selection */}
          <div className="em-form-section">
            <div className="em-form-section-title">Vendor Selection</div>
            <div className="grid">
              <div className="col-12 md:col-8">
                <label className="block mb-2 font-medium text-sm">Select Vendors*</label>
                {isVendorError && (
                  <div className="mb-2">
                    <Message
                      severity="error"
                      text={vendorError?.message ?? 'Failed to load vendors.'}
                      className="w-full"
                    />
                    <Button
                      label="Retry"
                      icon="pi pi-refresh"
                      severity="secondary"
                      size="small"
                      className="mt-1"
                      onClick={() => refetchVendors()}
                      aria-label="Retry loading vendors"
                    />
                  </div>
                )}
                <MultiSelect
                  value={selectedVendorIds}
                  options={vendorOptions}
                  onChange={(e) => setSelectedVendorIds(e.value)}
                  onFilter={handleVendorFilter}
                  filter
                  filterBy="label"
                  filterPlaceholder="Search vendors..."
                  placeholder="Select vendors"
                  className={`w-full ${validationErrors.vendors ? 'p-invalid' : ''}`}
                  display="chip"
                  maxSelectedLabels={5}
                  loading={isLoadingVendors}
                  virtualScrollerOptions={{ itemSize: 38 }}
                  emptyFilterMessage={isLoadingVendors ? 'Loading...' : 'No vendors found'}
                  aria-label="Select vendors for statement request"
                />
                {isLoadingVendors && (
                  <small className="text-color-secondary">
                    <ProgressSpinner style={{ width: '14px', height: '14px' }} /> Loading vendors...
                  </small>
                )}
                {validationErrors.vendors && (
                  <small className="p-error">{validationErrors.vendors}</small>
                )}
              </div>
            </div>
          </div>

          {/* Sender Settings */}
          <div className="em-form-section">
            <div className="em-form-section-title">Sender Settings</div>
            <div className="grid">
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Request Type*</label>
                <Dropdown
                  value={requestType}
                  options={requestTypeOptions}
                  onChange={(e) => setRequestType(e.value)}
                  className="w-full"
                />
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Upload & Share Options*</label>
                <Dropdown
                  value={uploadShareOption}
                  options={uploadShareOptions}
                  onChange={(e) => setUploadShareOption(e.value)}
                  className="w-full"
                />
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Import Statement via*</label>
                <Dropdown
                  value={importVia}
                  options={importViaOptions}
                  onChange={(e) => setImportVia(e.value)}
                  className="w-full"
                  placeholder="Select Browse File or SFTP"
                />
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Select Template*</label>
                <div className="flex gap-3 mt-2">
                  <div className="flex align-items-center gap-2">
                    <RadioButton value="Positive" onChange={(e) => setTemplate(e.value)} checked={template === 'Positive'} />
                    <label>Positive</label>
                  </div>
                  <div className="flex align-items-center gap-2">
                    <RadioButton value="Negative" onChange={(e) => setTemplate(e.value)} checked={template === 'Negative'} />
                    <label>Negative</label>
                  </div>
                </div>
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Start Date*</label>
                <Calendar
                  value={startDate}
                  onChange={(e) => setStartDate(e.value as Date)}
                  dateFormat="dd/mm/yy"
                  placeholder="DD/MM/YYYY"
                  className={`w-full ${validationErrors.startDate ? 'p-invalid' : ''}`}
                  showIcon
                  aria-label="Period start date"
                />
                {validationErrors.startDate && (
                  <small className="p-error">{validationErrors.startDate}</small>
                )}
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">End Date*</label>
                <Calendar
                  value={endDate}
                  onChange={(e) => setEndDate(e.value as Date)}
                  dateFormat="dd/mm/yy"
                  placeholder="DD/MM/YYYY"
                  className={`w-full ${validationErrors.endDate ? 'p-invalid' : ''}`}
                  showIcon
                  aria-label="Period end date"
                />
                {validationErrors.endDate && (
                  <small className="p-error">{validationErrors.endDate}</small>
                )}
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Select Branch*</label>
                <Dropdown
                  value={branch}
                  options={branchOptions}
                  onChange={(e) => setBranch(e.value)}
                  className="w-full"
                />
              </div>
              <div className="col-12">
                <label className="block mb-2 font-medium text-sm">Remarks (Optional)</label>
                <InputTextarea
                  value={remarks}
                  onChange={(e) => setRemarks(e.target.value)}
                  placeholder="Enter your remarks"
                  className="w-full"
                  rows={2}
                />
              </div>
            </div>
          </div>

          {/* Responder Settings */}
          <div className="em-form-section">
            <div className="em-form-section-title">Responder Settings</div>
            <div className="grid">
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Request Open Item Statement*</label>
                <div className="flex gap-3 mt-2">
                  <div className="flex align-items-center gap-2">
                    <RadioButton value="Yes" onChange={(e) => setRequestOpenItem(e.value)} checked={requestOpenItem === 'Yes'} />
                    <label>Yes</label>
                  </div>
                  <div className="flex align-items-center gap-2">
                    <RadioButton value="No" onChange={(e) => setRequestOpenItem(e.value)} checked={requestOpenItem === 'No'} />
                    <label>No</label>
                  </div>
                </div>
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Request Ledger Statement*</label>
                <div className="flex gap-3 mt-2">
                  <div className="flex align-items-center gap-2">
                    <RadioButton value="Yes" onChange={(e) => setRequestLedger(e.value)} checked={requestLedger === 'Yes'} />
                    <label>Yes</label>
                  </div>
                  <div className="flex align-items-center gap-2">
                    <RadioButton value="No" onChange={(e) => setRequestLedger(e.value)} checked={requestLedger === 'No'} />
                    <label>No</label>
                  </div>
                </div>
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Allow Party To Change Start Date & End Date*</label>
                <div className="flex gap-3 mt-2">
                  <div className="flex align-items-center gap-2">
                    <RadioButton value="Yes" onChange={(e) => setAllowDateChange(e.value)} checked={allowDateChange === 'Yes'} />
                    <label>Yes</label>
                  </div>
                  <div className="flex align-items-center gap-2">
                    <RadioButton value="No" onChange={(e) => setAllowDateChange(e.value)} checked={allowDateChange === 'No'} />
                    <label>No</label>
                  </div>
                </div>
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Acceptable File Format*</label>
                <div className="flex gap-3 mt-2">
                  <div className="flex align-items-center gap-2">
                    <RadioButton value="Excel Only" onChange={(e) => setFileFormat(e.value)} checked={fileFormat === 'Excel Only'} />
                    <label>Excel Only</label>
                  </div>
                  <div className="flex align-items-center gap-2">
                    <RadioButton value="Excel & All Formats" onChange={(e) => setFileFormat(e.value)} checked={fileFormat === 'Excel & All Formats'} />
                    <label>Excel & All Formats</label>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Reconciliation Settings */}
          <div className="em-form-section">
            <div className="em-form-section-title">Reconciliation Settings</div>
            <div className="grid">
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Amount Tolerance*</label>
                <div className="flex align-items-center gap-2">
                  <InputText value={amountTolerance} onChange={(e) => setAmountTolerance(e.target.value)} className="w-full" />
                  <span style={{ background: 'var(--color-primary)', color: '#fff', padding: '6px 10px', borderRadius: 'var(--radius-sm)', fontSize: 12 }}>%</span>
                </div>
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Select Date Range (in days)*</label>
                <div className="flex align-items-center gap-2">
                  <span className="text-sm">Min</span>
                  <InputText value={dateRangeMin} onChange={(e) => setDateRangeMin(e.target.value)} style={{ width: 60 }} />
                  <span className="text-sm">Max</span>
                  <InputText value={dateRangeMax} onChange={(e) => setDateRangeMax(e.target.value)} style={{ width: 60 }} />
                </div>
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">TDS Percentage*</label>
                <div className="flex align-items-center gap-2">
                  <span className="text-sm">Min</span>
                  <InputText value={tdsMin} onChange={(e) => setTdsMin(e.target.value)} style={{ width: 60 }} />
                  <span className="text-sm">%</span>
                  <span className="text-sm">Max</span>
                  <InputText value={tdsMax} onChange={(e) => setTdsMax(e.target.value)} style={{ width: 60 }} />
                  <span className="text-sm">%</span>
                </div>
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">GST Percentage*</label>
                <div className="flex align-items-center gap-2">
                  <InputText value={gstPercentage} onChange={(e) => setGstPercentage(e.target.value)} style={{ width: 80 }} />
                  <span className="text-sm">%</span>
                </div>
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Carry Forward Records from previous reco?*</label>
                <Dropdown
                  value={carryForward}
                  options={carryForwardOptions}
                  onChange={(e) => setCarryForward(e.value)}
                  className="w-full"
                />
              </div>
            </div>
          </div>

          {/* Email Settings */}
          <div className="em-form-section">
            <div className="em-form-section-title">Email Settings</div>
            <div className="grid">
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Send Email from*</label>
                <Dropdown
                  value={sendEmailFrom}
                  options={sendEmailFromOptions}
                  onChange={(e) => setSendEmailFrom(e.value)}
                  className="w-full"
                  placeholder="Select"
                  loading={isLoadingEmailConfig}
                  disabled={isLoadingEmailConfig || !emailConfigData?.is_configured}
                  tooltip={!emailConfigData?.is_configured ? 'Email not configured. Go to Settings > Email Configuration.' : undefined}
                />
                {isLoadingEmailConfig && (
                  <small className="text-color-secondary">
                    <ProgressSpinner style={{ width: '14px', height: '14px' }} /> Loading...
                  </small>
                )}
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Email Template*</label>
                <Dropdown
                  value={emailTemplate}
                  options={emailTemplateOptions}
                  onChange={(e) => setEmailTemplate(e.value)}
                  className="w-full"
                  placeholder="Select Email Template"
                  filter
                  showClear
                />
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Reminder Template*</label>
                <Dropdown
                  value={reminderTemplate}
                  options={reminderTemplateOptions}
                  onChange={(e) => setReminderTemplate(e.value)}
                  className="w-full"
                  placeholder="Select Reminder Group"
                  filter
                  showClear
                />
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Email Attachment</label>
                <Dropdown
                  value={emailAttachment}
                  options={emailAttachmentOptions}
                  onChange={(e) => setEmailAttachment(e.value)}
                  className="w-full"
                  placeholder="Select attachment"
                />
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Contact Person*</label>
                <Dropdown
                  value={contactPerson}
                  options={contactPersonOptions}
                  onChange={(e) => setContactPerson(e.value)}
                  className="w-full"
                  placeholder={selectedVendorIds.length === 0 ? 'Select vendors first' : 'Select contact'}
                  disabled={selectedVendorIds.length === 0 || isLoadingContacts}
                  loading={isLoadingContacts}
                  emptyMessage={selectedVendorIds.length === 0 ? 'Select vendors first' : 'No contacts found'}
                />
                {isLoadingContacts && (
                  <small className="text-color-secondary">
                    <ProgressSpinner style={{ width: '14px', height: '14px' }} /> Loading contacts...
                  </small>
                )}
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Send Now?*</label>
                <div className="flex gap-3 mt-2">
                  <div className="flex align-items-center gap-2">
                    <RadioButton value="Now" onChange={(e) => setSendNow(e.value)} checked={sendNow === 'Now'} />
                    <label>Now</label>
                  </div>
                  <div className="flex align-items-center gap-2">
                    <RadioButton value="Schedule" onChange={(e) => setSendNow(e.value)} checked={sendNow === 'Schedule'} />
                    <label>Schedule</label>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="flex justify-content-end gap-3 mt-4">
            <Button label="Preview" className="p-button-outlined" onClick={handlePreview} disabled={!emailTemplate} />
            <Button
              label="Submit"
              onClick={handleSubmit}
              loading={createMutation.isPending}
              disabled={createMutation.isPending}
              icon={createMutation.isPending ? 'pi pi-spin pi-spinner' : undefined}
            />
          </div>
        </div>
      )}

      {currentStep === 'upload' && (
        <div>
          <div className="em-form-section">
            <div className="em-form-section-title">Upload Ledger*</div>
            <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              From {startDate ? startDate.toLocaleDateString('en-GB') : 'DD-MM-YYYY'} To {endDate ? endDate.toLocaleDateString('en-GB') : 'DD-MM-YYYY'}
            </p>

            {/* Upload Progress */}
            {isUploading && uploadProgress > 0 && (
              <div className="mt-3 mb-3">
                <div className="flex align-items-center gap-2 mb-2">
                  <i className="pi pi-cloud-upload" />
                  <span className="text-sm">Uploading file...</span>
                </div>
                <ProgressBar value={uploadProgress} />
              </div>
            )}

            {/* File Upload Component */}
            <div className="mt-4">
              <FileUpload
                name="companyLedger"
                customUpload
                uploadHandler={async (event: FileUploadHandlerEvent) => {
                  const file = event.files[0];
                  if (!file) return;

                  if (!requestId) {
                    toast.current?.show({
                      severity: 'error',
                      summary: 'Upload Error',
                      detail: 'No request ID available. Please complete Step 1 first.',
                      life: 5000,
                    });
                    return;
                  }

                  try {
                    await uploadFile(file);
                    setUploadComplete(true);
                    toast.current?.show({
                      severity: 'success',
                      summary: 'Upload Complete',
                      detail: `${file.name} uploaded successfully. You can now track reconciliation.`,
                      life: 5000,
                    });
                  } catch (error: unknown) {
                    const errorMsg =
                      (error as { response?: { data?: { detail?: string } } })?.response?.data
                        ?.detail || 'Upload failed. Please try again.';
                    toast.current?.show({
                      severity: 'error',
                      summary: 'Upload Failed',
                      detail: errorMsg,
                      life: 8000,
                    });
                  }
                }}
                accept=".xlsx,.xls,.csv"
                maxFileSize={52428800}
                disabled={isUploading || !requestId}
                emptyTemplate={
                  <div className="flex flex-column align-items-center p-4">
                    <i
                      className="pi pi-cloud-upload"
                      style={{ fontSize: '3rem', color: 'var(--color-text-muted)' }}
                    />
                    <p style={{ color: 'var(--color-text-muted)', margin: '12px 0 0' }}>
                      Drag and drop files here, or click to browse
                    </p>
                    <p style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
                      Acceptable file types: .xlsx, .xls, .csv | Max size: 50MB
                    </p>
                  </div>
                }
                chooseLabel="Browse File"
                uploadLabel="Upload"
                cancelLabel="Clear"
              />
            </div>

            {/* Success — View Reconciliation */}
            {uploadComplete && requestId && !inviteSent && (
              <div className="flex align-items-center gap-3 mt-4 p-3" style={{ background: 'var(--blue-50, #eff6ff)', borderRadius: 'var(--radius-md)', border: '1px solid var(--blue-200, #bfdbfe)' }}>
                <i className="pi pi-envelope" style={{ fontSize: '1.5rem', color: 'var(--blue-500)' }} />
                <div className="flex-1">
                  <p className="m-0 font-medium">Company ledger uploaded</p>
                  <p className="m-0 text-sm" style={{ color: 'var(--color-text-muted)' }}>
                    Click "Send Vendor Invite" to email the vendor(s) a link to upload their statement.
                  </p>
                </div>
                <Button
                  label="Send Vendor Invite"
                  icon="pi pi-send"
                  loading={isSendingInvites}
                  onClick={handleSendInvites}
                />
              </div>
            )}

            {inviteSent && requestId && (
              <div className="flex align-items-center gap-3 mt-4 p-3" style={{ background: 'var(--green-50, #f0fdf4)', borderRadius: 'var(--radius-md)', border: '1px solid var(--green-200, #bbf7d0)' }}>
                <i className="pi pi-check-circle" style={{ fontSize: '1.5rem', color: 'var(--green-500)' }} />
                <div className="flex-1">
                  <p className="m-0 font-medium">Vendor invite sent successfully</p>
                  <p className="m-0 text-sm" style={{ color: 'var(--color-text-muted)' }}>
                    The vendor(s) have been emailed a unique link to upload their statement. You can track progress in Track Reconciliation.
                  </p>
                </div>
                <Button
                  label="View Reconciliation"
                  icon="pi pi-arrow-right"
                  iconPos="right"
                  onClick={() => navigate(`/track-reconciliation/${requestId}`)}
                />
              </div>
            )}
          </div>

          <div className="flex justify-content-end gap-3 mt-4">
            <Button label="Back" className="p-button-outlined" onClick={() => setCurrentStep('configure')} />
            <Button label="Preview" className="p-button-outlined" onClick={handlePreview} disabled={!emailTemplate} />
          </div>
        </div>
      )}

      {/* Email Preview Dialog */}
      <Dialog
        header="Email Preview"
        visible={previewVisible}
        onHide={() => setPreviewVisible(false)}
        style={{ width: '70vw', maxWidth: '900px' }}
        maximizable
        modal
      >
        {previewLoading && (
          <div className="flex justify-content-center align-items-center" style={{ minHeight: '200px' }}>
            <ProgressSpinner style={{ width: '40px', height: '40px' }} />
          </div>
        )}
        {previewError && (
          <Message severity="error" text={previewError} className="w-full" />
        )}
        {!previewLoading && !previewError && previewHtml && (
          <div
            className="email-preview-content"
            style={{ border: '1px solid var(--surface-border)', borderRadius: '6px', padding: '1rem', background: '#fff' }}
            dangerouslySetInnerHTML={{ __html: previewHtml }}
          />
        )}
        {!previewLoading && !previewError && !previewHtml && (
          <p className="text-color-secondary text-center">No preview content available.</p>
        )}
      </Dialog>

      <Toast ref={toast} />
    </div>
  );
};
