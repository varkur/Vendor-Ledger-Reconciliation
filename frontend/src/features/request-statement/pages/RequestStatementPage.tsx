/**
 * Request Statement page — Multi-step form for creating a new party request.
 * Step 1: Configure (sender settings, responder settings, reconciliation settings, email settings)
 * Step 2: Upload Statement
 */

import { useState } from 'react';
import { InputText } from 'primereact/inputtext';
import { Dropdown } from 'primereact/dropdown';
import { RadioButton } from 'primereact/radiobutton';
import { Calendar } from 'primereact/calendar';
import { InputTextarea } from 'primereact/inputtextarea';
import { Button } from 'primereact/button';

type Step = 'configure' | 'upload';

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
                  className="w-full"
                />
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
                  className="w-full"
                  showIcon
                />
              </div>
              <div className="col-12 md:col-4">
                <label className="block mb-2 font-medium text-sm">End Date*</label>
                <Calendar
                  value={endDate}
                  onChange={(e) => setEndDate(e.value as Date)}
                  dateFormat="dd/mm/yy"
                  placeholder="DD/MM/YYYY"
                  className="w-full"
                  showIcon
                />
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
            <Button label="Submit" onClick={() => setCurrentStep('upload')} />
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
