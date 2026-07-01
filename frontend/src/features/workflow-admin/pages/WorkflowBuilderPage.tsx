/**
 * Workflow Builder page.
 * Define statuses and transitions for a workflow definition.
 */
import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputText } from 'primereact/inputtext';
import { InputSwitch } from 'primereact/inputswitch';
import { InputNumber } from 'primereact/inputnumber';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { workflowApi, type WorkflowDefinition, type WorkflowStatus, type WorkflowTransition } from '../api/workflowApi';

export const WorkflowBuilderPage = () => {
  const { definitionId } = useParams<{ definitionId: string }>();
  const toast = useRef<Toast>(null);
  const [definition, setDefinition] = useState<WorkflowDefinition | null>(null);
  const [statuses, setStatuses] = useState<WorkflowStatus[]>([]);
  const [transitions, setTransitions] = useState<WorkflowTransition[]>([]);
  const [loading, setLoading] = useState(true);

  // Status form
  const [showStatusDialog, setShowStatusDialog] = useState(false);
  const [statusForm, setStatusForm] = useState({ code: '', name: '', is_initial: false, is_terminal: false, sequence: 0 });

  // Transition form
  const [showTransitionDialog, setShowTransitionDialog] = useState(false);
  const [transitionForm, setTransitionForm] = useState({ from_status_id: '', to_status_id: '', action_code: '', requires_comment: false });

  useEffect(() => { if (definitionId) loadData(); }, [definitionId]);

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await workflowApi.getDefinition(definitionId!);
      setDefinition(data.definition);
      setStatuses(data.statuses);
      setTransitions(data.transitions);
    } catch (e: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed to load', life: 5000 });
    } finally {
      setLoading(false);
    }
  };

  const handleCreateStatus = async () => {
    try {
      await workflowApi.createStatus(definitionId!, statusForm);
      setShowStatusDialog(false);
      setStatusForm({ code: '', name: '', is_initial: false, is_terminal: false, sequence: 0 });
      toast.current?.show({ severity: 'success', summary: 'Added', detail: 'Status added', life: 3000 });
      loadData();
    } catch (e: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed', life: 5000 });
    }
  };

  const handleCreateTransition = async () => {
    try {
      await workflowApi.createTransition(definitionId!, transitionForm);
      setShowTransitionDialog(false);
      setTransitionForm({ from_status_id: '', to_status_id: '', action_code: '', requires_comment: false });
      toast.current?.show({ severity: 'success', summary: 'Added', detail: 'Transition added', life: 3000 });
      loadData();
    } catch (e: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed', life: 5000 });
    }
  };

  const handleDeleteTransition = async (id: string) => {
    try {
      await workflowApi.deleteTransition(id);
      toast.current?.show({ severity: 'success', summary: 'Deleted', detail: 'Transition removed', life: 3000 });
      loadData();
    } catch (e: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to delete', life: 5000 });
    }
  };

  const statusOptions = statuses.map((s) => ({ label: `${s.name} (${s.code})`, value: s.id }));

  const getStatusName = (id: string) => statuses.find((s) => s.id === id)?.name || id;

  const statusTypeTemplate = (row: WorkflowStatus) => {
    if (row.is_initial) return <Tag value="Initial" severity="info" />;
    if (row.is_terminal) return <Tag value="Terminal" severity="danger" />;
    return <Tag value="Normal" severity="success" />;
  };

  const transitionActionsTemplate = (row: WorkflowTransition) => (
    <Button icon="pi pi-trash" rounded outlined severity="danger" size="small" onClick={() => handleDeleteTransition(row.id)} tooltip="Delete" />
  );

  if (loading) return <div className="p-3"><i className="pi pi-spin pi-spinner" /> Loading...</div>;

  return (
    <div className="p-3">
      <Toast ref={toast} />

      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">
          Workflow Builder: {definition?.name}
        </h2>
        <p className="text-600 mt-1 mb-0">
          {definition?.code} — {definition?.entity_type}
        </p>
      </div>

      {/* Statuses Section */}
      <div className="surface-card p-3 border-round shadow-1 mb-3">
        <div className="flex align-items-center justify-content-between mb-3">
          <h3 className="text-lg font-semibold m-0">Statuses (States)</h3>
          <Button label="Add Status" icon="pi pi-plus" size="small" onClick={() => setShowStatusDialog(true)} />
        </div>
        <DataTable value={statuses} stripedRows emptyMessage="No statuses defined" size="small">
          <Column field="sequence" header="#" style={{ width: '3rem' }} />
          <Column field="code" header="Code" />
          <Column field="name" header="Name" />
          <Column header="Type" body={statusTypeTemplate} />
        </DataTable>
      </div>

      {/* Transitions Section */}
      <div className="surface-card p-3 border-round shadow-1">
        <div className="flex align-items-center justify-content-between mb-3">
          <h3 className="text-lg font-semibold m-0">Transitions (State Machine)</h3>
          <Button label="Add Transition" icon="pi pi-plus" size="small" onClick={() => setShowTransitionDialog(true)} disabled={statuses.length < 2} />
        </div>
        <DataTable value={transitions} stripedRows emptyMessage="No transitions defined" size="small">
          <Column header="From" body={(row) => <Tag value={getStatusName(row.from_status_id)} />} />
          <Column field="action_code" header="Action" />
          <Column header="To" body={(row) => <Tag value={getStatusName(row.to_status_id)} severity="success" />} />
          <Column field="requires_comment" header="Comment?" body={(row) => row.requires_comment ? 'Yes' : 'No'} />
          <Column header="" body={transitionActionsTemplate} style={{ width: '4rem' }} />
        </DataTable>
      </div>

      {/* Add Status Dialog */}
      <Dialog header="Add Status" visible={showStatusDialog} onHide={() => setShowStatusDialog(false)} style={{ width: '400px' }} modal
        footer={<div className="flex justify-content-end gap-2">
          <Button label="Cancel" severity="secondary" text onClick={() => setShowStatusDialog(false)} />
          <Button label="Add" icon="pi pi-check" onClick={handleCreateStatus} disabled={!statusForm.code || !statusForm.name} />
        </div>}
      >
        <div className="flex flex-column gap-3 mt-2">
          <div className="flex flex-column gap-2">
            <label className="font-medium">Code</label>
            <InputText value={statusForm.code} onChange={(e) => setStatusForm({ ...statusForm, code: e.target.value.toUpperCase().replace(/\s/g, '_') })} placeholder="e.g. DRAFT" />
          </div>
          <div className="flex flex-column gap-2">
            <label className="font-medium">Name</label>
            <InputText value={statusForm.name} onChange={(e) => setStatusForm({ ...statusForm, name: e.target.value })} placeholder="e.g. Draft" />
          </div>
          <div className="flex flex-column gap-2">
            <label className="font-medium">Sequence</label>
            <InputNumber value={statusForm.sequence} onValueChange={(e) => setStatusForm({ ...statusForm, sequence: e.value || 0 })} />
          </div>
          <div className="flex align-items-center gap-3">
            <InputSwitch checked={statusForm.is_initial} onChange={(e) => setStatusForm({ ...statusForm, is_initial: e.value ?? false })} />
            <label className="font-medium">Initial State</label>
          </div>
          <div className="flex align-items-center gap-3">
            <InputSwitch checked={statusForm.is_terminal} onChange={(e) => setStatusForm({ ...statusForm, is_terminal: e.value ?? false })} />
            <label className="font-medium">Terminal State (final)</label>
          </div>
        </div>
      </Dialog>

      {/* Add Transition Dialog */}
      <Dialog header="Add Transition" visible={showTransitionDialog} onHide={() => setShowTransitionDialog(false)} style={{ width: '450px' }} modal
        footer={<div className="flex justify-content-end gap-2">
          <Button label="Cancel" severity="secondary" text onClick={() => setShowTransitionDialog(false)} />
          <Button label="Add" icon="pi pi-check" onClick={handleCreateTransition} disabled={!transitionForm.from_status_id || !transitionForm.to_status_id || !transitionForm.action_code} />
        </div>}
      >
        <div className="flex flex-column gap-3 mt-2">
          <div className="flex flex-column gap-2">
            <label className="font-medium">From Status</label>
            <Dropdown value={transitionForm.from_status_id} options={statusOptions} onChange={(e) => setTransitionForm({ ...transitionForm, from_status_id: e.value })} placeholder="Select source state" className="w-full" />
          </div>
          <div className="flex flex-column gap-2">
            <label className="font-medium">Action Code</label>
            <InputText value={transitionForm.action_code} onChange={(e) => setTransitionForm({ ...transitionForm, action_code: e.target.value.toUpperCase().replace(/\s/g, '_') })} placeholder="e.g. APPROVE, REJECT, SUBMIT" />
          </div>
          <div className="flex flex-column gap-2">
            <label className="font-medium">To Status</label>
            <Dropdown value={transitionForm.to_status_id} options={statusOptions} onChange={(e) => setTransitionForm({ ...transitionForm, to_status_id: e.value })} placeholder="Select target state" className="w-full" />
          </div>
          <div className="flex align-items-center gap-3">
            <InputSwitch checked={transitionForm.requires_comment} onChange={(e) => setTransitionForm({ ...transitionForm, requires_comment: e.value ?? false })} />
            <label className="font-medium">Requires Comment</label>
          </div>
        </div>
      </Dialog>
    </div>
  );
};
