/**
 * Edit Party page — Full-page form for editing vendor details with tabbed sections.
 * Matches Firmway's "Edit Party" screen layout.
 */

import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { TabView, TabPanel } from 'primereact/tabview';
import { InputText } from 'primereact/inputtext';
import { Dropdown } from 'primereact/dropdown';
import { Button } from 'primereact/button';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { useVendor, useUpdateVendor } from '../hooks/useVendors';
import { VendorContactResponse } from '../api/vendorApi';
import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';

const PARTY_TYPE_OPTIONS = [
  { label: 'Vendor', value: 'vendor' },
  { label: 'Customer', value: 'customer' },
];

const STATUS_OPTIONS = [
  { label: 'Active', value: 'active' },
  { label: 'Inactive', value: 'inactive' },
];

const CATEGORY_OPTIONS = [
  { label: 'A', value: 'A' },
  { label: 'B', value: 'B' },
  { label: 'C', value: 'C' },
];

const FREQUENCY_OPTIONS = [
  { label: 'Daily', value: 'Daily' },
  { label: 'Weekly', value: 'Weekly' },
  { label: 'Monthly', value: 'Monthly' },
  { label: 'Quarterly', value: 'Quarterly' },
  { label: 'Yearly', value: 'Yearly' },
];

const MSME_CLASS_OPTIONS = [
  { label: 'Micro', value: 'Micro' },
  { label: 'Small', value: 'Small' },
  { label: 'Medium', value: 'Medium' },
  { label: 'Not Registered', value: 'Not Registered' },
];

const MSME_TYPE_OPTIONS = [
  { label: 'Service', value: 'Service' },
  { label: 'Manufacturing', value: 'Manufacturing' },
];

interface ContactRow {
  id?: string;
  name: string;
  email: string;
  phone: string;
  workPhone: string;
}

interface ErpCodeRow {
  id?: string;
  erpName: string;
  erpCode: string;
}

export const EditPartyPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { companyCode } = useSelectedEntity();
  const { data: vendor, isLoading } = useVendor(id, companyCode);
  const updateVendorMutation = useUpdateVendor();

  // Top section form state
  const [partyType, setPartyType] = useState('vendor');
  const [partyCode, setPartyCode] = useState('');
  const [partyName, setPartyName] = useState('');
  const [contactName, setContactName] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [contactMobile, setContactMobile] = useState('');
  const [contactWorkPhone, setContactWorkPhone] = useState('');
  const [status, setStatus] = useState('active');

  // Reconciliation Settings tab
  const [category, setCategory] = useState<string | null>(null);
  const [frequency, setFrequency] = useState<string | null>(null);
  const [gstPercentage, setGstPercentage] = useState('');
  const [tdsMin, setTdsMin] = useState('');
  const [tdsMax, setTdsMax] = useState('');

  // Contact Person tab
  const [contacts, setContacts] = useState<ContactRow[]>([]);

  // Internal Team tab
  const [owner, setOwner] = useState<string | null>(null);
  const [reviewer1, setReviewer1] = useState<string | null>(null);
  const [reviewer2, setReviewer2] = useState<string | null>(null);
  const [businessUser, setBusinessUser] = useState<string | null>(null);

  // Other Details tab
  const [pan, setPan] = useState('');
  const [gstin, setGstin] = useState('');
  const [msmeClass, setMsmeClass] = useState<string | null>(null);
  const [msmeType, setMsmeType] = useState<string | null>(null);
  const [udhyamNumber, setUdhyamNumber] = useState('');

  // ERP Code tab
  const [erpCodes, setErpCodes] = useState<ErpCodeRow[]>([]);

  // Load vendor data into form
  useEffect(() => {
    if (vendor) {
      setPartyCode(vendor.vendor_code || '');
      setPartyName(vendor.name || '');
      setStatus(vendor.status || 'active');
      setPan(vendor.pan || '');
      setGstin(vendor.gstin || '');

      // Map contacts
      if (vendor.contacts && vendor.contacts.length > 0) {
        const primary = vendor.contacts.find((c: VendorContactResponse) => c.is_primary) || vendor.contacts[0];
        if (primary) {
          setContactName(primary.name || '');
          setContactEmail(primary.email || '');
          setContactMobile(primary.phone || '');
        }

        setContacts(
          vendor.contacts.map((c: VendorContactResponse) => ({
            id: c.id,
            name: c.name || '',
            email: c.email || '',
            phone: c.phone || '',
            workPhone: '',
          }))
        );
      }
    }
  }, [vendor]);

  const handleSave = () => {
    if (!id) return;

    // Sync top-section contact fields into contacts array
    const updatedContacts = [...contacts];
    if (updatedContacts.length > 0) {
      updatedContacts[0] = {
        ...updatedContacts[0],
        name: contactName,
        email: contactEmail,
        phone: contactMobile,
        workPhone: contactWorkPhone,
      };
    } else if (contactName || contactEmail) {
      updatedContacts.push({
        name: contactName,
        email: contactEmail,
        phone: contactMobile,
        workPhone: contactWorkPhone,
      });
    }

    updateVendorMutation.mutate(
      {
        id,
        data: {
          name: partyName,
          status,
          pan: pan || null,
          gstin: gstin || null,
          city: null,
          contacts: updatedContacts.map((c) => ({
            name: c.name,
            email: c.email,
            phone: c.phone || undefined,
          })),
        },
        companyCode: companyCode,
      },
      {
        onSuccess: () => {
          navigate('/manage-party');
        },
      }
    );
  };

  const handleAddContact = () => {
    setContacts([...contacts, { name: '', email: '', phone: '', workPhone: '' }]);
  };

  const handleDeleteContact = (index: number) => {
    setContacts(contacts.filter((_, i) => i !== index));
  };

  const handleDeleteErpCode = (index: number) => {
    setErpCodes(erpCodes.filter((_, i) => i !== index));
  };

  if (isLoading) {
    return (
      <div className="p-4">
        <p>Loading...</p>
      </div>
    );
  }

  // Team member options placeholder (would come from API)
  const teamMemberOptions: { label: string; value: string }[] = [];

  return (
    <div className="edit-party-page">
      {/* Header */}
      <div className="em-page-header" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <Button
          icon="pi pi-arrow-left"
          className="p-button-text p-button-plain"
          onClick={() => navigate('/manage-party')}
          aria-label="Back to Manage Party"
        />
        <h2 style={{ margin: 0 }}>Edit Party</h2>
      </div>

      {/* Top Section: Core fields */}
      <div className="em-card" style={{ padding: '1.5rem', marginBottom: '1rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
          <div className="field">
            <label htmlFor="partyType">Party Type *</label>
            <Dropdown
              id="partyType"
              value={partyType}
              options={PARTY_TYPE_OPTIONS}
              onChange={(e) => setPartyType(e.value)}
              placeholder="Select Party Type"
              style={{ width: '100%' }}
            />
          </div>
          <div className="field">
            <label htmlFor="partyCode">Party Code *</label>
            <InputText
              id="partyCode"
              value={partyCode}
              readOnly
              style={{ width: '100%', backgroundColor: '#f5f5f5' }}
            />
          </div>
          <div className="field">
            <label htmlFor="partyName">Party Name *</label>
            <InputText
              id="partyName"
              value={partyName}
              onChange={(e) => setPartyName(e.target.value)}
              style={{ width: '100%' }}
            />
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
          <div className="field">
            <label htmlFor="contactName">Contact Person Name *</label>
            <InputText
              id="contactName"
              value={contactName}
              onChange={(e) => setContactName(e.target.value)}
              style={{ width: '100%' }}
            />
          </div>
          <div className="field">
            <label htmlFor="contactEmail">Contact Person Email *</label>
            <InputText
              id="contactEmail"
              value={contactEmail}
              onChange={(e) => setContactEmail(e.target.value)}
              style={{ width: '100%' }}
            />
          </div>
          <div className="field">
            <label htmlFor="contactMobile">Contact Person Mobile</label>
            <InputText
              id="contactMobile"
              value={contactMobile}
              onChange={(e) => setContactMobile(e.target.value)}
              style={{ width: '100%' }}
            />
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
          <div className="field">
            <label htmlFor="contactWorkPhone">Contact Person Work Phone</label>
            <InputText
              id="contactWorkPhone"
              value={contactWorkPhone}
              onChange={(e) => setContactWorkPhone(e.target.value)}
              style={{ width: '100%' }}
            />
          </div>
          <div className="field">
            <label htmlFor="status">Status *</label>
            <Dropdown
              id="status"
              value={status}
              options={STATUS_OPTIONS}
              onChange={(e) => setStatus(e.value)}
              placeholder="Select Status"
              style={{ width: '100%' }}
            />
          </div>
          <div />
        </div>
      </div>

      {/* Tab Panel */}
      <div className="em-card" style={{ padding: '1rem', marginBottom: '1rem' }}>
        <TabView>
          {/* Tab 1: Reconciliation Settings */}
          <TabPanel header="Reconciliation Settings">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', padding: '1rem 0' }}>
              <div className="field">
                <label htmlFor="category">Category</label>
                <Dropdown
                  id="category"
                  value={category}
                  options={CATEGORY_OPTIONS}
                  onChange={(e) => setCategory(e.value)}
                  placeholder="Select Category"
                  style={{ width: '100%' }}
                />
              </div>
              <div className="field">
                <label htmlFor="frequency">Frequency</label>
                <Dropdown
                  id="frequency"
                  value={frequency}
                  options={FREQUENCY_OPTIONS}
                  onChange={(e) => setFrequency(e.value)}
                  placeholder="Select Frequency"
                  style={{ width: '100%' }}
                />
              </div>
              <div className="field">
                <label htmlFor="gstPercentage">GST Percentage</label>
                <div className="p-inputgroup">
                  <InputText
                    id="gstPercentage"
                    value={gstPercentage}
                    onChange={(e) => setGstPercentage(e.target.value)}
                    placeholder="0"
                  />
                  <span className="p-inputgroup-addon">%</span>
                </div>
              </div>
              <div className="field">
                <label>TDS Percentage</label>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <div className="p-inputgroup" style={{ flex: 1 }}>
                    <InputText
                      value={tdsMin}
                      onChange={(e) => setTdsMin(e.target.value)}
                      placeholder="Minimum"
                    />
                    <span className="p-inputgroup-addon">%</span>
                  </div>
                  <div className="p-inputgroup" style={{ flex: 1 }}>
                    <InputText
                      value={tdsMax}
                      onChange={(e) => setTdsMax(e.target.value)}
                      placeholder="Maximum"
                    />
                    <span className="p-inputgroup-addon">%</span>
                  </div>
                </div>
              </div>
            </div>
          </TabPanel>

          {/* Tab 2: Contact Person */}
          <TabPanel header="Contact Person">
            <div style={{ padding: '1rem 0' }}>
              <div style={{ marginBottom: '1rem', textAlign: 'right' }}>
                <Button
                  label="Add Contact"
                  icon="pi pi-plus"
                  className="p-button-sm"
                  onClick={handleAddContact}
                />
              </div>
              <DataTable value={contacts} emptyMessage="No contacts added.">
                <Column
                  field="name"
                  header="Name"
                  body={(rowData, { rowIndex }) => (
                    <InputText
                      value={rowData.name}
                      onChange={(e) => {
                        const updated = [...contacts];
                        const current = updated[rowIndex];
                        if (!current) return;
                        updated[rowIndex] = { ...current, name: e.target.value };
                        setContacts(updated);
                      }}
                      style={{ width: '100%', border: 'none', background: 'transparent' }}
                      placeholder="Enter name"
                    />
                  )}
                />
                <Column
                  field="email"
                  header="Email"
                  body={(rowData, { rowIndex }) => (
                    <InputText
                      value={rowData.email}
                      onChange={(e) => {
                        const updated = [...contacts];
                        const current = updated[rowIndex];
                        if (!current) return;
                        updated[rowIndex] = { ...current, email: e.target.value };
                        setContacts(updated);
                      }}
                      style={{ width: '100%', border: 'none', background: 'transparent' }}
                      placeholder="Enter email"
                    />
                  )}
                />
                <Column
                  field="phone"
                  header="Mobile"
                  body={(rowData, { rowIndex }) => (
                    <InputText
                      value={rowData.phone}
                      onChange={(e) => {
                        const updated = [...contacts];
                        const current = updated[rowIndex];
                        if (!current) return;
                        updated[rowIndex] = { ...current, phone: e.target.value };
                        setContacts(updated);
                      }}
                      style={{ width: '100%', border: 'none', background: 'transparent' }}
                      placeholder="Enter mobile"
                    />
                  )}
                />
                <Column
                  field="workPhone"
                  header="Work Phone"
                  body={(rowData, { rowIndex }) => (
                    <InputText
                      value={rowData.workPhone}
                      onChange={(e) => {
                        const updated = [...contacts];
                        const current = updated[rowIndex];
                        if (!current) return;
                        updated[rowIndex] = { ...current, workPhone: e.target.value };
                        setContacts(updated);
                      }}
                      style={{ width: '100%', border: 'none', background: 'transparent' }}
                      placeholder="Enter work phone"
                    />
                  )}
                />
                <Column
                  header="Action"
                  body={(_, { rowIndex }) => (
                    <Button
                      icon="pi pi-trash"
                      className="p-button-rounded p-button-danger p-button-sm"
                      style={{ color: 'white' }}
                      onClick={() => handleDeleteContact(rowIndex)}
                      aria-label="Delete contact"
                    />
                  )}
                  style={{ width: '80px', textAlign: 'center' }}
                />
              </DataTable>
            </div>
          </TabPanel>

          {/* Tab 3: Internal Team */}
          <TabPanel header="Internal Team">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', padding: '1rem 0' }}>
              <div className="field">
                <label htmlFor="owner">Owner</label>
                <Dropdown
                  id="owner"
                  value={owner}
                  options={teamMemberOptions}
                  onChange={(e) => setOwner(e.value)}
                  placeholder="Select Owner"
                  style={{ width: '100%' }}
                />
              </div>
              <div className="field">
                <label htmlFor="reviewer1">Reviewer 1</label>
                <Dropdown
                  id="reviewer1"
                  value={reviewer1}
                  options={teamMemberOptions}
                  onChange={(e) => setReviewer1(e.value)}
                  placeholder="Select Reviewer 1"
                  style={{ width: '100%' }}
                />
              </div>
              <div className="field">
                <label htmlFor="reviewer2">Reviewer 2</label>
                <Dropdown
                  id="reviewer2"
                  value={reviewer2}
                  options={teamMemberOptions}
                  onChange={(e) => setReviewer2(e.value)}
                  placeholder="Select Reviewer 2"
                  style={{ width: '100%' }}
                />
              </div>
              <div className="field">
                <label htmlFor="businessUser">Business User</label>
                <Dropdown
                  id="businessUser"
                  value={businessUser}
                  options={teamMemberOptions}
                  onChange={(e) => setBusinessUser(e.value)}
                  placeholder="Select Business User"
                  style={{ width: '100%' }}
                />
              </div>
            </div>
          </TabPanel>

          {/* Tab 4: Other Details */}
          <TabPanel header="Other Details">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', padding: '1rem 0' }}>
              <div className="field">
                <label htmlFor="pan">PAN</label>
                <InputText
                  id="pan"
                  value={pan}
                  onChange={(e) => setPan(e.target.value)}
                  style={{ width: '100%' }}
                />
              </div>
              <div className="field">
                <label htmlFor="gstin">GSTIN</label>
                <InputText
                  id="gstin"
                  value={gstin}
                  onChange={(e) => setGstin(e.target.value)}
                  style={{ width: '100%' }}
                />
              </div>
              <div className="field">
                <label htmlFor="msmeClass">MSME Class</label>
                <Dropdown
                  id="msmeClass"
                  value={msmeClass}
                  options={MSME_CLASS_OPTIONS}
                  onChange={(e) => setMsmeClass(e.value)}
                  placeholder="Select MSME Class"
                  style={{ width: '100%' }}
                />
              </div>
              <div className="field">
                <label htmlFor="msmeType">MSME Type</label>
                <Dropdown
                  id="msmeType"
                  value={msmeType}
                  options={MSME_TYPE_OPTIONS}
                  onChange={(e) => setMsmeType(e.value)}
                  placeholder="Select MSME Type"
                  style={{ width: '100%' }}
                />
              </div>
              <div className="field">
                <label htmlFor="udhyamNumber">Udhyam Registration Number</label>
                <InputText
                  id="udhyamNumber"
                  value={udhyamNumber}
                  onChange={(e) => setUdhyamNumber(e.target.value)}
                  style={{ width: '100%' }}
                />
              </div>
            </div>
          </TabPanel>

          {/* Tab 5: ERP Code */}
          <TabPanel header="ERP Code">
            <div style={{ padding: '1rem 0' }}>
              <DataTable value={erpCodes} emptyMessage="No ERP codes configured.">
                <Column field="erpName" header="ERP Name" />
                <Column field="erpCode" header="ERP Code" />
                <Column
                  header="Action"
                  body={(_, { rowIndex }) => (
                    <Button
                      icon="pi pi-trash"
                      className="p-button-rounded p-button-danger p-button-sm"
                      style={{ color: 'white' }}
                      onClick={() => handleDeleteErpCode(rowIndex)}
                      aria-label="Delete ERP code"
                    />
                  )}
                  style={{ width: '80px', textAlign: 'center' }}
                />
              </DataTable>
            </div>
          </TabPanel>
        </TabView>
      </div>

      {/* Footer */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', padding: '1rem 0' }}>
        <Button
          label="Cancel"
          className="p-button-outlined"
          onClick={() => navigate('/manage-party')}
        />
        <Button
          label="Save"
          icon="pi pi-check"
          onClick={handleSave}
          loading={updateVendorMutation.isPending}
        />
      </div>
    </div>
  );
};
