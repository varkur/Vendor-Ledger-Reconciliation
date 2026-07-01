/**
 * Workflow Definitions list page.
 * Create and view workflow definitions.
 */
import { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { Dialog } from 'primereact/dialog';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { Toolbar } from 'primereact/toolbar';
import { useNavigate } from 'react-router-dom';
import { workflowApi, type WorkflowDefinition } from '../api/workflowApi';

export const WorkflowDefinitionsPage = () => {
  const toast = useRef<Toast>(null);
  const navigate = useNavigate();
  const [definitions, setDefinitions] = useState<WorkflowDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ code: '', name: '', description: '', entity_type: '' });

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await workflowApi.listDefinitions();
      setDefinitions(data.definitions);
    } catch (e: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed to load', life: 5000 });
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    try {
      await workflowApi.createDefinition(form);
      setShowCreate(false);
      setForm({ code: '', name: '', description: '', entity_type: '' });
      toast.current?.show({ severity: 'success', summary: 'Created', detail: `Workflow '${form.code}' created`, life: 3000 });
      loadData();
    } catch (e: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed', life: 5000 });
    }
  };

  const statusTemplate = (row: WorkflowDefinition) => (
    <Tag value={row.is_active ? 'Active' : 'Inactive'} severity={row.is_active ? 'success' : 'danger'} />
  );

  const actionsTemplate = (row: WorkflowDefinition) => (
    <Button
      icon="pi pi-cog"
      rounded
      outlined
      severity="info"
      size="small"
      tooltip="Configure"
      onClick={() => navigate(`/workflow-builder/${row.id}`)}
    />
  );

  return (
    <div className="p-3">
      <Toast ref={toast} />
      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Workflow Definitions</h2>
        <p className="text-600 mt-1 mb-0">Define and manage approval workflows</p>
      </div>

      <div className="surface-card p-3 border-round shadow-1">
        <Toolbar className="mb-3" start={() => (
          <div className="flex gap-2">
            <Button label="New Workflow" icon="pi pi-plus" onClick={() => setShowCreate(true)} />
            <Button label="Refresh" icon="pi pi-refresh" severity="secondary" outlined onClick={loadData} />
          </div>
        )} />

        <DataTable value={definitions} loading={loading} stripedRows paginator rows={10} emptyMessage="No workflows defined">
          <Column field="code" header="Code" sortable />
          <Column field="name" header="Name" sortable />
          <Column field="entity_type" header="Entity Type" sortable />
          <Column field="version" header="Version" />
          <Column header="Status" body={statusTemplate} />
          <Column header="Actions" body={actionsTemplate} style={{ width: '5rem' }} />
        </DataTable>
      </div>

      <Dialog header="Create Workflow" visible={showCreate} onHide={() => setShowCreate(false)} style={{ width: '450px' }} modal
        footer={<div className="flex justify-content-end gap-2">
          <Button label="Cancel" severity="secondary" text onClick={() => setShowCreate(false)} />
          <Button label="Create" icon="pi pi-check" onClick={handleCreate} disabled={!form.code || !form.name || !form.entity_type} />
        </div>}
      >
        <div className="flex flex-column gap-3 mt-2">
          <div className="flex flex-column gap-2">
            <label className="font-medium">Code</label>
            <InputText value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase().replace(/\s/g, '_') })} placeholder="e.g. COMMISSION_CLAIM" />
          </div>
          <div className="flex flex-column gap-2">
            <label className="font-medium">Name</label>
            <InputText value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Commission Claim Approval" />
          </div>
          <div className="flex flex-column gap-2">
            <label className="font-medium">Entity Type</label>
            <InputText value={form.entity_type} onChange={(e) => setForm({ ...form, entity_type: e.target.value })} placeholder="e.g. commission_claim" />
          </div>
          <div className="flex flex-column gap-2">
            <label className="font-medium">Description</label>
            <InputTextarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} rows={2} />
          </div>
        </div>
      </Dialog>
    </div>
  );
};
