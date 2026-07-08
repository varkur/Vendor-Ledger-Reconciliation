/**
 * Request Statement page — Multi-step form for creating a new party request.
 * Step 1: Configure (sender settings, responder settings, reconciliation settings, email settings)
 * Step 2: Upload Statement
 *
 * Wired to backend APIs:
 * - POST /api/v1/vlr/requests (create reconciliation request with vendor_ids)
 * - GET /api/v1/vlr/vendors (fetch vendor list for selection)
 *
 * Implements loading indicators, error handling, and form validation.
 *
 * Requirements: 23.3, 25.1, 25.2
 */

import { useState, useCallback, useMemo } from 'react';
import { InputText } from 'primereact/inputtext';
import { Dropdown } from 'primereact/dropdown';
import { RadioButton } from 'primereact/radiobutton';
import { Calendar } from 'primereact/calendar';
import { InputTextarea } from 'primereact/inputtextarea';
import { Button } from 'primereact/button';
import { MultiSelect } from 'primereact/multiselect';
import { Message } from 'primereact/message';
import { ProgressSpinner } from 'primereact/progressspinner';

import { useVendorSelection, useCreateStatementRequest } from '../hooks/useRequestStatement';

type Step = 'configure' | 'upload';

const DEFAULT_COMPANY_CODE = '1000';
const DEFAULT_FISCAL_YEAR = '2024-25';

export const RequestStatementPage = () => {
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
  const [sendNow, setSendNow] = useState('Now');

  // Success state
  const [showSuccess, setShowSuccess] = useState(false);

  // Validation errors
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  // ─── API Hooks ───────────────────────────────────────────────────────────────
  const {
    data: vendorData,
    isLoading: isLoadingVendors,
    isError: isVendorError,
    error: vendorError,
    refetch: refetchVendors,
  } = useVendorSelection(DEFAULT_COMPANY_CODE, vendorSearch);

  const createMutation = useCreateStatementRequest();

  // ─── Derived Data ────────────────────────────────────────────────────────────
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
        company_code: DEFAULT_COMPANY_CODE,
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
          setShowSuccess(true);
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

  const handleResetSuccess = useCallback(() => {
    setShowSuccess(false);
    setTitle('');
    setSelectedVendorIds([]);
    setStartDate(null);
    setEndDate(null);
    setRemarks('');
    setCurrentStep('configure');
    createMutation.reset();
  }, [createMutation]);

  // ─── Success State ──────────────────────────────────────────────────────────
  if (showSuccess && createMutation.isSuccess) {
    return (
      <div>
        <h2>New Party Request</h2>
        <div className="em-form-section">
          <div className="flex flex-column align-items-center justify-content-center p-5">
            <i
              className="pi pi-check-circle"
              style={{ fontSize: '3rem', color: 'var(--green-500)' }}
            />
            <h3 className="mt-3 mb-1">Statement Request Created Successfully</h3>
            <p className="text-color-secondary text-center" style={{ maxWidth: '500px' }}>
              Your request has been submitted for {selectedVendorIds.length} vendor(s).
              The reconciliation workflow will begin processing shortly.
            </p>
            <p className="text-sm text-color-secondary">
              Request ID: {createMutation.data?.id}
            </p>
            <Button
              label="Create Another Request"
              icon="pi pi-plus"
              className="mt-3"
              onClick={handleResetSuccess}
            />
          </div>
        </div>
      </div>
    );
  }

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
                  filterPlaceholder="Search vendors..."
                  placeholder="Select vendors"
                  className={`w-full ${validationErrors.vendors ? 'p-invalid' : ''}`}
                  display="chip"
                  maxSelectedLabels={5}
                  loading={isLoadingVendors}
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
                  options={[{ label: 'Select', value: '' }]}
                  onChange={(e) => setSendEmailFrom(e.value)}
                  className="w-full"
                  placeholder="Select"
                />
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Email Template*</label>
                <Dropdown
                  value={emailTemplate}
                  options={[{ label: 'null', value: '' }]}
                  onChange={(e) => setEmailTemplate(e.value)}
                  className="w-full"
                  placeholder="null"
                />
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Reminder Template*</label>
                <Dropdown
                  value={reminderTemplate}
                  options={[{ label: 'null', value: '' }]}
                  onChange={(e) => setReminderTemplate(e.value)}
                  className="w-full"
                  placeholder="null"
                />
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Email Attachment</label>
                <Dropdown
                  value=""
                  options={[{ label: 'select', value: '' }]}
                  onChange={() => {}}
                  className="w-full"
                  placeholder="select"
                />
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">Contact Person*</label>
                <Dropdown
                  value={contactPerson}
                  options={[{ label: 'Select', value: '' }]}
                  onChange={(e) => setContactPerson(e.value)}
                  className="w-full"
                  placeholder="Select"
                />
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
            <Button label="Preview" className="p-button-outlined" />
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
            <div className="flex align-items-center justify-content-between mt-4 p-4" style={{ border: '1px dashed var(--color-surface-border)', borderRadius: 'var(--radius-md)' }}>
              <div>
                <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
                  Acceptable file types: xls, xlsx, xlsb, csv
                </p>
                <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
                  Max size: 50mb
                </p>
              </div>
              <Button label="Browse File" className="btn-accent" />
            </div>
          </div>

          <div className="flex justify-content-end gap-3 mt-4">
            <Button label="Back" className="p-button-outlined" onClick={() => setCurrentStep('configure')} />
            <Button label="Preview" className="p-button-outlined" />
          </div>
        </div>
      )}
    </div>
  );
};
