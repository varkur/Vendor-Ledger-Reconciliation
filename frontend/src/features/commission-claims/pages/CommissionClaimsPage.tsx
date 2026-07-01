/**
 * Commission Claims page — Example module demonstrating workflow integration.
 * Shows claim lifecycle: Create → Submit → Approve/Reject through the workflow engine.
 */

import { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputNumber } from 'primereact/inputnumber';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { Toolbar } from 'primereact/toolbar';
import { apiClient } from '@shared/services/apiClient';

interface Claim {
  id: string;
  claim_number: string;
  employee_name: string;
  amount: number;
  company: string;
  department: string;
  region: string;
  status: string;
  workflow_instance_id: string | null;
  created_by: string;
  created_date: string;
}

interface ClaimDetail {
  claim: Claim;
  workflow_status: { status_code: string; status_name: string; is_terminal: boolean } | null;
  available_actions: { action_code: string; requires_comment: boolean }[];
}

export const CommissionClaimsPage = () => {
  const toast = useRef<Toast>(null);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showActions, setShowActions] = useState(false);
  const [selectedClaim, setSelectedClaim] = useState<ClaimDetail | null>(null);
  const [actionComment, setActionComment] = useState('');

  const [form, setForm] = useState({ employee_name: '', amount: 0, company: '', department: '', region: '', description: '' });

  useEffect(() => { loadClaims(); }, []);

  const loadClaims = async () => {
    setLoading(true);
    try {
      const { data } = await apiClient.get<{ claims: Claim[]; total: number }>('/claims');
      setClaims(data.claims);
    } catch {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to load claims', life: 5000 });
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    try {
      await apiClient.post('/claims', form);
      setShowCreate(false);
      setForm({ employee_name: '', amount: 0, company: '', department: '', region: '', description: '' });
      toast.current?.show({ severity: 'success', summary: 'Created', detail: 'Claim created in DRAFT', life: 3000 });
      loadClaims();
    } catch (e: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed', life: 5000 });
    }
  };

  const handleSubmit = async (claimId: string) => {
    try {
      await apiClient.post(`/claims/${claimId}/submit`);
      toast.current?.show({ severity: 'success', summary: 'Submitted', detail: 'Workflow started', life: 3000 });
      loadClaims();
    } catch (e: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed to submit', life: 5000 });
    }
  };

  const openActions = async (claim: Claim) => {
    try {
      const { data } = await apiClient.get<ClaimDetail>(`/claims/${claim.id}`);
      setSelectedClaim(data);
      setActionComment('');
      setShowActions(true);
    } catch {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to load details', life: 5000 });
    }
  };

  const executeAction = async (actionCode: string) => {
    if (!selectedClaim) return;
    try {
      const { data } = await apiClient.post(`/claims/${selectedClaim.claim.id}/action`, null, {
        params: { action_code: actionCode, comments: actionComment },
      });
      toast.current?.show({
        severity: 'success',
        summary: `${actionCode}`,
        detail: `Status → ${data.current_status}`,
        life: 3000,
      });
      setShowActions(false);
      loadClaims();
    } catch (e: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Action failed', life: 5000 });
    }
  };

  const statusTemplate = (row: Claim) => {
    const colors: Record<string, 'info' | 'success' | 'warning' | 'danger'> = {
      DRAFT: 'info',
      SUBMITTED: 'warning',
      L1_PENDING: 'warning',
      L2_PENDING: 'warning',
      APPROVED: 'success',
      REJECTED: 'danger',
      CANCELLED: 'danger',
      CLOSED: 'info',
    };
    return <Tag value={row.status} severity={colors[row.status] || 'info'} />;
  };

  const amountTemplate = (row: Claim) => (
    <span className="font-semibold">₹{Number(row.amount).toLocaleString()}</span>
  );

  const actionsTemplate = (row: Claim) => (
    <div className="flex gap-1">
      {row.status === 'DRAFT' && (
        <Button icon="pi pi-send" rounded outlined severity="success" size="small" tooltip="Submit" onClick={() => handleSubmit(row.id)} />
      )}
      {row.workflow_instance_id && !['APPROVED', 'REJECTED', 'CANCELLED', 'CLOSED'].includes(row.status) && (
        <Button icon="pi pi-bolt" rounded outlined severity="warning" size="small" tooltip="Actions" onClick={() => openActions(row)} />
      )}
      {['APPROVED', 'REJECTED', 'CANCELLED', 'CLOSED'].includes(row.status) && (
        <Button icon="pi pi-eye" rounded outlined severity="secondary" size="small" tooltip="View" onClick={() => openActions(row)} />
      )}
    </div>
  );

  return (
    <div className="p-3">
      <Toast ref={toast} />
      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Commission Claims</h2>
        <p className="text-600 mt-1 mb-0">Example module — Create claims and process through the workflow engine</p>
      </div>

      <div className="surface-card p-3 border-round shadow-1">
        <Toolbar className="mb-3" start={() => (
          <div className="flex gap-2">
            <Button label="New Claim" icon="pi pi-plus" onClick={() => setShowCreate(true)} />
            <Button label="Refresh" icon="pi pi-refresh" severity="secondary" outlined onClick={loadClaims} />
          </div>
        )} />

        <DataTable value={claims} loading={loading} stripedRows paginator rows={10} emptyMessage="No claims yet — create one to test the workflow">
          <Column field="claim_number" header="Claim #" sortable />
          <Column field="employee_name" header="Employee" sortable />
          <Column header="Amount" body={amountTemplate} sortable field="amount" />
          <Column field="company" header="Company" />
          <Column header="Status" body={statusTemplate} sortable field="status" />
          <Column field="created_by" header="Created By" />
          <Column header="Actions" body={actionsTemplate} style={{ width: '8rem' }} />
        </DataTable>
      </div>

      {/* Create Claim Dialog */}
      <Dialog header="Create Commission Claim" visible={showCreate} onHide={() => setShowCreate(false)} style={{ width: '500px' }} modal
        footer={<div className="flex justify-content-end gap-2">
          <Button label="Cancel" severity="secondary" text onClick={() => setShowCreate(false)} />
          <Button label="Create" icon="pi pi-check" onClick={handleCreate} disabled={!form.employee_name || !form.amount || !form.company} />
        </div>}
      >
        <div className="flex flex-column gap-3 mt-2">
          <div className="grid">
            <div className="col-6 flex flex-column gap-2">
              <label className="font-medium">Employee Name</label>
              <InputText value={form.employee_name} onChange={(e) => setForm({ ...form, employee_name: e.target.value })} placeholder="John Doe" />
            </div>
            <div className="col-6 flex flex-column gap-2">
              <label className="font-medium">Amount (₹)</label>
              <InputNumber value={form.amount} onValueChange={(e) => setForm({ ...form, amount: e.value || 0 })} mode="currency" currency="INR" locale="en-IN" />
            </div>
            <div className="col-6 flex flex-column gap-2">
              <label className="font-medium">Company</label>
              <Dropdown value={form.company} options={[{ label: 'Emcure', value: 'Emcure' }, { label: 'Zuventus', value: 'Zuventus' }, { label: 'Marcan', value: 'Marcan' }]} onChange={(e) => setForm({ ...form, company: e.value })} placeholder="Select company" className="w-full" />
            </div>
            <div className="col-6 flex flex-column gap-2">
              <label className="font-medium">Department</label>
              <InputText value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} placeholder="Sales" />
            </div>
            <div className="col-6 flex flex-column gap-2">
              <label className="font-medium">Region</label>
              <InputText value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} placeholder="West" />
            </div>
          </div>
          <div className="flex flex-column gap-2">
            <label className="font-medium">Description</label>
            <InputTextarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} rows={2} placeholder="Claim details..." />
          </div>
        </div>
      </Dialog>

      {/* Workflow Actions Dialog */}
      <Dialog
        header={`Claim ${selectedClaim?.claim.claim_number || ''} — Workflow Actions`}
        visible={showActions}
        onHide={() => setShowActions(false)}
        style={{ width: '500px' }}
        modal
      >
        {selectedClaim && (
          <div className="flex flex-column gap-3">
            {/* Claim Summary */}
            <div className="surface-ground p-3 border-round">
              <div className="grid">
                <div className="col-6"><strong>Amount:</strong> ₹{Number(selectedClaim.claim.amount).toLocaleString()}</div>
                <div className="col-6"><strong>Company:</strong> {selectedClaim.claim.company}</div>
                <div className="col-6"><strong>Employee:</strong> {selectedClaim.claim.employee_name}</div>
                <div className="col-6"><strong>Current Status:</strong> <Tag value={selectedClaim.workflow_status?.status_code || selectedClaim.claim.status} /></div>
              </div>
            </div>

            {/* Available Actions */}
            {selectedClaim.available_actions.length > 0 ? (
              <>
                <div className="flex flex-column gap-2">
                  <label className="font-medium">Comments</label>
                  <InputTextarea value={actionComment} onChange={(e) => setActionComment(e.target.value)} rows={2} placeholder="Optional comments..." />
                </div>
                <div className="flex gap-2 flex-wrap">
                  {selectedClaim.available_actions.map((action) => {
                    const severities: Record<string, 'success' | 'danger' | 'warning' | 'info'> = {
                      APPROVE: 'success',
                      REJECT: 'danger',
                      REFER_BACK: 'warning',
                      CANCEL: 'danger',
                      CLOSE: 'info',
                    };
                    return (
                      <Button
                        key={action.action_code}
                        label={action.action_code.replace('_', ' ')}
                        severity={severities[action.action_code] || 'info'}
                        onClick={() => executeAction(action.action_code)}
                        size="small"
                      />
                    );
                  })}
                </div>
              </>
            ) : (
              <p className="text-600 m-0">No actions available — workflow is in a terminal state.</p>
            )}
          </div>
        )}
      </Dialog>
    </div>
  );
};
