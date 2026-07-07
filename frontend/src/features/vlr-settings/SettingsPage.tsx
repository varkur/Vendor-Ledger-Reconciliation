/**
 * Settings & Configuration page — VLR system configuration.
 * Sections: Tolerance Config, Matching Preferences, Notification Intervals,
 *           Approval Thresholds, TDS/GST Defaults, SAP Connection
 */

import { useState } from 'react';
import { InputText } from 'primereact/inputtext';
import { InputNumber } from 'primereact/inputnumber';
import { Dropdown } from 'primereact/dropdown';
import { Button } from 'primereact/button';
import { InputSwitch } from 'primereact/inputswitch';
import { Password } from 'primereact/password';
import { Toast } from 'primereact/toast';
import { useRef } from 'react';

export const SettingsPage = () => {
  const toast = useRef<Toast>(null);

  // Tolerance Configuration
  const [amountTolerance, setAmountTolerance] = useState<number | null>(500);
  const [percentTolerance, setPercentTolerance] = useState<number | null>(2);
  const [dateTolerance, setDateTolerance] = useState<number | null>(3);

  // Matching Preferences
  const [matchingMethod, setMatchingMethod] = useState('auto');
  const [autoMatchThreshold, setAutoMatchThreshold] = useState<number | null>(95);
  const [enableFuzzyMatch, setEnableFuzzyMatch] = useState(true);

  // Notification Intervals
  const [reminderInterval, setReminderInterval] = useState<number | null>(7);
  const [maxReminders, setMaxReminders] = useState<number | null>(3);
  const [escalationDays, setEscalationDays] = useState<number | null>(15);

  // Approval Thresholds
  const [autoApproveLimit, setAutoApproveLimit] = useState<number | null>(10000);
  const [managerApproveLimit, setManagerApproveLimit] = useState<number | null>(500000);
  const [requireDualApproval, setRequireDualApproval] = useState(true);

  // TDS/GST Defaults
  const [defaultTdsRate, setDefaultTdsRate] = useState<number | null>(2);
  const [defaultGstRate, setDefaultGstRate] = useState<number | null>(18);
  const [tdsThreshold, setTdsThreshold] = useState<number | null>(30000);

  // SAP Connection
  const [sapHost, setSapHost] = useState('sap-prod.company.local');
  const [sapClient, setSapClient] = useState('100');
  const [sapUsername, setSapUsername] = useState('VLR_SERVICE');
  const [sapPassword, setSapPassword] = useState('');
  const [sapSystemNumber, setSapSystemNumber] = useState('00');

  const matchingMethods = [
    { label: 'Automatic (AI-based)', value: 'auto' },
    { label: 'Rule-based', value: 'rules' },
    { label: 'Manual Only', value: 'manual' },
  ];

  const handleSave = () => {
    toast.current?.show({ severity: 'success', summary: 'Settings Saved', detail: 'Configuration has been updated successfully.' });
  };

  const handleTestConnection = () => {
    toast.current?.show({ severity: 'info', summary: 'Testing Connection', detail: 'SAP connection test in progress...' });
    setTimeout(() => {
      toast.current?.show({ severity: 'success', summary: 'Connection Successful', detail: 'SAP system is reachable.' });
    }, 2000);
  };

  return (
    <div>
      <Toast ref={toast} />

      {/* Page Header */}
      <div className="em-page-header">
        <h2>Settings & Configuration</h2>
        <div className="em-page-header-actions">
          <Button label="Save All Settings" icon="pi pi-save" onClick={handleSave} />
        </div>
      </div>

      <div className="grid">
        {/* Tolerance Configuration */}
        <div className="col-12 md:col-6">
          <div className="em-card">
            <h3 style={{ marginTop: 0, marginBottom: 16 }}>
              <i className="pi pi-sliders-h mr-2" />Tolerance Configuration
            </h3>
            <div className="flex flex-column gap-3">
              <div>
                <label htmlFor="amount-tolerance" style={{ display: 'block', fontWeight: 500, marginBottom: 6 }}>
                  Amount Tolerance (₹)
                </label>
                <InputNumber
                  id="amount-tolerance"
                  value={amountTolerance}
                  onValueChange={(e) => setAmountTolerance(e.value ?? null)}
                  mode="currency"
                  currency="INR"
                  locale="en-IN"
                  className="w-full"
                />
              </div>
              <div>
                <label htmlFor="percent-tolerance" style={{ display: 'block', fontWeight: 500, marginBottom: 6 }}>
                  Percentage Tolerance (%)
                </label>
                <InputNumber
                  id="percent-tolerance"
                  value={percentTolerance}
                  onValueChange={(e) => setPercentTolerance(e.value ?? null)}
                  suffix="%"
                  min={0}
                  max={100}
                  className="w-full"
                />
              </div>
              <div>
                <label htmlFor="date-tolerance" style={{ display: 'block', fontWeight: 500, marginBottom: 6 }}>
                  Date Tolerance (days)
                </label>
                <InputNumber
                  id="date-tolerance"
                  value={dateTolerance}
                  onValueChange={(e) => setDateTolerance(e.value ?? null)}
                  suffix=" days"
                  min={0}
                  max={30}
                  className="w-full"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Matching Preferences */}
        <div className="col-12 md:col-6">
          <div className="em-card">
            <h3 style={{ marginTop: 0, marginBottom: 16 }}>
              <i className="pi pi-link mr-2" />Matching Preferences
            </h3>
            <div className="flex flex-column gap-3">
              <div>
                <label htmlFor="matching-method" style={{ display: 'block', fontWeight: 500, marginBottom: 6 }}>
                  Matching Method
                </label>
                <Dropdown
                  id="matching-method"
                  value={matchingMethod}
                  options={matchingMethods}
                  onChange={(e) => setMatchingMethod(e.value)}
                  className="w-full"
                />
              </div>
              <div>
                <label htmlFor="auto-match-threshold" style={{ display: 'block', fontWeight: 500, marginBottom: 6 }}>
                  Auto-Match Confidence Threshold (%)
                </label>
                <InputNumber
                  id="auto-match-threshold"
                  value={autoMatchThreshold}
                  onValueChange={(e) => setAutoMatchThreshold(e.value ?? null)}
                  suffix="%"
                  min={50}
                  max={100}
                  className="w-full"
                />
              </div>
              <div className="flex align-items-center gap-2">
                <InputSwitch checked={enableFuzzyMatch} onChange={(e) => setEnableFuzzyMatch(e.value)} />
                <label>Enable Fuzzy Matching</label>
              </div>
            </div>
          </div>
        </div>

        {/* Notification Intervals */}
        <div className="col-12 md:col-6">
          <div className="em-card">
            <h3 style={{ marginTop: 0, marginBottom: 16 }}>
              <i className="pi pi-bell mr-2" />Notification Intervals
            </h3>
            <div className="flex flex-column gap-3">
              <div>
                <label htmlFor="reminder-interval" style={{ display: 'block', fontWeight: 500, marginBottom: 6 }}>
                  Reminder Interval (days)
                </label>
                <InputNumber
                  id="reminder-interval"
                  value={reminderInterval}
                  onValueChange={(e) => setReminderInterval(e.value ?? null)}
                  suffix=" days"
                  min={1}
                  max={30}
                  className="w-full"
                />
              </div>
              <div>
                <label htmlFor="max-reminders" style={{ display: 'block', fontWeight: 500, marginBottom: 6 }}>
                  Maximum Reminders
                </label>
                <InputNumber
                  id="max-reminders"
                  value={maxReminders}
                  onValueChange={(e) => setMaxReminders(e.value ?? null)}
                  min={1}
                  max={10}
                  className="w-full"
                />
              </div>
              <div>
                <label htmlFor="escalation-days" style={{ display: 'block', fontWeight: 500, marginBottom: 6 }}>
                  Auto-Escalation After (days)
                </label>
                <InputNumber
                  id="escalation-days"
                  value={escalationDays}
                  onValueChange={(e) => setEscalationDays(e.value ?? null)}
                  suffix=" days"
                  min={1}
                  max={60}
                  className="w-full"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Approval Thresholds */}
        <div className="col-12 md:col-6">
          <div className="em-card">
            <h3 style={{ marginTop: 0, marginBottom: 16 }}>
              <i className="pi pi-check-circle mr-2" />Approval Thresholds
            </h3>
            <div className="flex flex-column gap-3">
              <div>
                <label htmlFor="auto-approve-limit" style={{ display: 'block', fontWeight: 500, marginBottom: 6 }}>
                  Auto-Approve Limit (₹)
                </label>
                <InputNumber
                  id="auto-approve-limit"
                  value={autoApproveLimit}
                  onValueChange={(e) => setAutoApproveLimit(e.value ?? null)}
                  mode="currency"
                  currency="INR"
                  locale="en-IN"
                  className="w-full"
                />
              </div>
              <div>
                <label htmlFor="manager-approve-limit" style={{ display: 'block', fontWeight: 500, marginBottom: 6 }}>
                  Manager Approval Limit (₹)
                </label>
                <InputNumber
                  id="manager-approve-limit"
                  value={managerApproveLimit}
                  onValueChange={(e) => setManagerApproveLimit(e.value ?? null)}
                  mode="currency"
                  currency="INR"
                  locale="en-IN"
                  className="w-full"
                />
              </div>
              <div className="flex align-items-center gap-2">
                <InputSwitch checked={requireDualApproval} onChange={(e) => setRequireDualApproval(e.value)} />
                <label>Require Dual Approval (above manager limit)</label>
              </div>
            </div>
          </div>
        </div>

        {/* TDS/GST Defaults */}
        <div className="col-12 md:col-6">
          <div className="em-card">
            <h3 style={{ marginTop: 0, marginBottom: 16 }}>
              <i className="pi pi-percentage mr-2" />TDS/GST Defaults
            </h3>
            <div className="flex flex-column gap-3">
              <div>
                <label htmlFor="default-tds-rate" style={{ display: 'block', fontWeight: 500, marginBottom: 6 }}>
                  Default TDS Rate (%)
                </label>
                <InputNumber
                  id="default-tds-rate"
                  value={defaultTdsRate}
                  onValueChange={(e) => setDefaultTdsRate(e.value ?? null)}
                  suffix="%"
                  min={0}
                  max={30}
                  className="w-full"
                />
              </div>
              <div>
                <label htmlFor="default-gst-rate" style={{ display: 'block', fontWeight: 500, marginBottom: 6 }}>
                  Default GST Rate (%)
                </label>
                <InputNumber
                  id="default-gst-rate"
                  value={defaultGstRate}
                  onValueChange={(e) => setDefaultGstRate(e.value ?? null)}
                  suffix="%"
                  min={0}
                  max={28}
                  className="w-full"
                />
              </div>
              <div>
                <label htmlFor="tds-threshold" style={{ display: 'block', fontWeight: 500, marginBottom: 6 }}>
                  TDS Threshold (₹)
                </label>
                <InputNumber
                  id="tds-threshold"
                  value={tdsThreshold}
                  onValueChange={(e) => setTdsThreshold(e.value ?? null)}
                  mode="currency"
                  currency="INR"
                  locale="en-IN"
                  className="w-full"
                />
              </div>
            </div>
          </div>
        </div>

        {/* SAP Connection Settings */}
        <div className="col-12 md:col-6">
          <div className="em-card">
            <h3 style={{ marginTop: 0, marginBottom: 16 }}>
              <i className="pi pi-server mr-2" />SAP Connection Settings
            </h3>
            <div className="flex flex-column gap-3">
              <div>
                <label htmlFor="sap-host" style={{ display: 'block', fontWeight: 500, marginBottom: 6 }}>
                  SAP Host
                </label>
                <InputText
                  id="sap-host"
                  value={sapHost}
                  onChange={(e) => setSapHost(e.target.value)}
                  className="w-full"
                />
              </div>
              <div className="flex gap-2">
                <div className="flex-1">
                  <label htmlFor="sap-client" style={{ display: 'block', fontWeight: 500, marginBottom: 6 }}>
                    Client
                  </label>
                  <InputText
                    id="sap-client"
                    value={sapClient}
                    onChange={(e) => setSapClient(e.target.value)}
                    className="w-full"
                  />
                </div>
                <div className="flex-1">
                  <label htmlFor="sap-system" style={{ display: 'block', fontWeight: 500, marginBottom: 6 }}>
                    System Number
                  </label>
                  <InputText
                    id="sap-system"
                    value={sapSystemNumber}
                    onChange={(e) => setSapSystemNumber(e.target.value)}
                    className="w-full"
                  />
                </div>
              </div>
              <div>
                <label htmlFor="sap-username" style={{ display: 'block', fontWeight: 500, marginBottom: 6 }}>
                  Username
                </label>
                <InputText
                  id="sap-username"
                  value={sapUsername}
                  onChange={(e) => setSapUsername(e.target.value)}
                  className="w-full"
                />
              </div>
              <div>
                <label htmlFor="sap-password" style={{ display: 'block', fontWeight: 500, marginBottom: 6 }}>
                  Password
                </label>
                <Password
                  id="sap-password"
                  value={sapPassword}
                  onChange={(e) => setSapPassword(e.target.value)}
                  className="w-full"
                  toggleMask
                  feedback={false}
                  placeholder="••••••••"
                />
              </div>
              <Button
                label="Test Connection"
                icon="pi pi-bolt"
                className="p-button-outlined"
                onClick={handleTestConnection}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
