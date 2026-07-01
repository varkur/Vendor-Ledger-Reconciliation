/**
 * Approval Matrix Management page.
 * Define and edit rules and approval levels.
 */
import { useEffect, useRef, useState } from 'react';
import { Button } from 'primereact/button';
import { Column } from 'primereact/column';
import { DataTable } from 'primereact/datatable';
import { Dialog } from 'primereact/dialog';
import { Dropdown } from 'primereact/dropdown';
import { InputText } from 'primereact/inputtext';
import { InputNumber } from 'primereact/inputnumber';
import { MultiSelect } from 'primereact/multiselect';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { Toolbar } from 'primereact/toolbar';
import { apiClient } from '@shared/services/apiClient';
import { workflowApi, type ApprovalMatrix } from '../api/workflowApi';

const OPERATORS = [
  { label: 'Equals', value: 'EQ' },
  { label: 'Not Equals', value: 'NEQ' },
  { label: 'Greater Than', value: 'GT' },
  { label: 'Greater or Equal', value: 'GTE' },
  { label: 'Less Than', value: 'LT' },
  { label: 'Less or Equal', value: 'LTE' },
  { label: 'Contains', value: 'CONTAINS' },
  { label: 'In List', value: 'IN' },
];

const DATA_TYPES = [
  { label: 'String', value: 'STRING' },
  { label: 'Number', value: 'NUMBER' },
  { label: 'Boolean', value: 'BOOLEAN' },
  { label: 'List', value: 'LIST' },
];

interface RuleRow { field: string; operator: string; value: string; data_type: string; logical_group: string }
interface AssignmentRow { level: number; assignment_type: string; user_ids: string[]; role_ids: string[] }

interface SelectOption { label: string; value: string }

export const ApprovalMatrixPage = () => {
  const toast = useRef<Toast>(null);
  const [matrices, setMatrices] = useState<ApprovalMatrix[]>([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingMatrix, setEditingMatrix] = useState<ApprovalMatrix | null>(null);

  const [form, setForm] = useState({ code: '', name: '', entity_type: '', priority: 0 });
  const [rules, setRules] = useState<RuleRow[]>([]);
  const [assignments, setAssignments] = useState<AssignmentRow[]>([]);

  // Roles and Users for dropdowns
  const [roleOptions, setRoleOptions] = useState<SelectOption[]>([]);
  const [userOptions, setUserOptions] = useState<SelectOption[]>([]);

  useEffect(() => { loadData(); loadRolesAndUsers(); }, []);

  const loadRolesAndUsers = async () => {
    try {
      const [rolesRes, usersRes] = await Promise.all([
        apiClient.get<{ roles: { id: string; code: string; name: string }[] }>('/rbac/roles'),
        apiClient.get<{ users: { id: string; username: string }[] }>('/users?limit=500'),
      ]);
      setRoleOptions(rolesRes.data.roles.map((r) => ({ label: `${r.name} (${r.code})`, value: r.id })));
      setUserOptions(usersRes.data.users.map((u) => ({ label: u.username, value: u.id })));
    } catch {
      // Fallback — empty options
    }
  };

  const loadData = async () => {
    setLoading(true);
    try {
      const data = await workflowApi.listMatrices();
      setMatrices(data);
    } catch {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to load', life: 5000 });
    } finally {
      setLoading(false);
    }
  };

  const openCreate = () => {
    setEditingMatrix(null);
    setForm({ code: '', name: '', entity_type: '', priority: 0 });
    setRules([]);
    setAssignments([]);
    setShowDialog(true);
  };

  const openEdit = (matrix: ApprovalMatrix) => {
    setEditingMatrix(matrix);
    setForm({ code: matrix.code, name: matrix.name, entity_type: matrix.entity_type, priority: matrix.priority });
    setRules(matrix.rules.map((r) => ({ ...r })));
    setAssignments(matrix.assignments.map((a) => ({
      level: a.level,
      assignment_type: a.assignment_type,
      user_ids: a.user_id ? [a.user_id] : [],
      role_ids: a.role_id ? [a.role_id] : [],
    })));
    setShowDialog(true);
  };

  const addRule = () => setRules([...rules, { field: '', operator: 'EQ', value: '', data_type: 'STRING', logical_group: 'default' }]);
  const removeRule = (idx: number) => setRules(rules.filter((_, i) => i !== idx));

  const addAssignment = () => setAssignments([...assignments, { level: assignments.length + 1, assignment_type: 'ROLE', user_ids: [], role_ids: [] }]);
  const removeAssignment = (idx: number) => setAssignments(assignments.filter((_, i) => i !== idx));

  const handleSave = async () => {
    const payload = {
      ...form,
      rules: rules.filter((r) => r.field && r.value),
      assignments: assignments.map((a) => ({
        level: a.level,
        assignment_type: a.assignment_type,
        user_id: a.assignment_type === 'USER' && a.user_ids.length > 0 ? a.user_ids[0] : null,
        role_id: a.assignment_type === 'ROLE' && a.role_ids.length > 0 ? a.role_ids[0] : null,
      })),
    };

    try {
      if (editingMatrix) {
        await workflowApi.updateMatrix(editingMatrix.id, payload);
        toast.current?.show({ severity: 'success', summary: 'Updated', detail: `Matrix '${form.code}' updated`, life: 3000 });
      } else {
        await workflowApi.createMatrix(payload);
        toast.current?.show({ severity: 'success', summary: 'Created', detail: `Matrix '${form.code}' created`, life: 3000 });
      }
      setShowDialog(false);
      loadData();
    } catch (e: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: e.response?.data?.detail || 'Failed', life: 5000 });
    }
  };

  const rulesTemplate = (row: ApprovalMatrix) => (
    <span>{row.rules.length} rule{row.rules.length !== 1 ? 's' : ''}</span>
  );

  const levelsTemplate = (row: ApprovalMatrix) => (
    <span>{row.assignments.length} level{row.assignments.length !== 1 ? 's' : ''}</span>
  );

  const actionsTemplate = (row: ApprovalMatrix) => (
    <Button
      icon="pi pi-pencil"
      rounded
      outlined
      severity="info"
      size="small"
      tooltip="Edit"
      onClick={() => openEdit(row)}
    />
  );

  const isEditMode = editingMatrix !== null;

  return (
    <div className="p-3">
      <Toast ref={toast} />
      <div className="mb-3">
        <h2 className="text-xl font-semibold text-900 m-0">Approval Matrix</h2>
        <p className="text-600 mt-1 mb-0">Configure dynamic approval routing rules</p>
      </div>

      <div className="surface-card p-3 border-round shadow-1">
        <Toolbar className="mb-3" start={() => (
          <div className="flex gap-2">
            <Button label="New Matrix" icon="pi pi-plus" onClick={openCreate} />
            <Button label="Refresh" icon="pi pi-refresh" severity="secondary" outlined onClick={loadData} />
          </div>
        )} />

        <DataTable value={matrices} loading={loading} stripedRows paginator rows={10} emptyMessage="No approval matrices defined">
          <Column field="code" header="Code" sortable />
          <Column field="name" header="Name" sortable />
          <Column field="entity_type" header="Entity Type" />
          <Column field="priority" header="Priority" />
          <Column header="Rules" body={rulesTemplate} />
          <Column header="Levels" body={levelsTemplate} />
          <Column header="Status" body={(row) => <Tag value={row.is_active ? 'Active' : 'Inactive'} severity={row.is_active ? 'success' : 'danger'} />} />
          <Column header="Actions" body={actionsTemplate} style={{ width: '5rem' }} />
        </DataTable>
      </div>

      {/* Create / Edit Matrix Dialog */}
      <Dialog
        header={isEditMode ? `Edit Matrix: ${editingMatrix?.code}` : 'Create Approval Matrix'}
        visible={showDialog}
        onHide={() => setShowDialog(false)}
        style={{ width: '700px' }}
        modal
        footer={<div className="flex justify-content-end gap-2">
          <Button label="Cancel" severity="secondary" text onClick={() => setShowDialog(false)} />
          <Button label={isEditMode ? 'Save Changes' : 'Create'} icon="pi pi-check" onClick={handleSave} disabled={!form.code || !form.name || !form.entity_type} />
        </div>}
      >
        <div className="flex flex-column gap-4 mt-2">
          {/* Basic Info */}
          <div className="grid">
            <div className="col-6 flex flex-column gap-2">
              <label className="font-medium">Code</label>
              <InputText value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase().replace(/\s/g, '_') })} placeholder="e.g. COMMISSION_AMOUNT" disabled={isEditMode} />
            </div>
            <div className="col-6 flex flex-column gap-2">
              <label className="font-medium">Name</label>
              <InputText value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Amount Based Approval" />
            </div>
            <div className="col-6 flex flex-column gap-2">
              <label className="font-medium">Entity Type</label>
              <InputText value={form.entity_type} onChange={(e) => setForm({ ...form, entity_type: e.target.value })} placeholder="commission_claim" />
            </div>
            <div className="col-6 flex flex-column gap-2">
              <label className="font-medium">Priority</label>
              <InputNumber value={form.priority} onValueChange={(e) => setForm({ ...form, priority: e.value || 0 })} />
            </div>
          </div>

          {/* Rules */}
          <div>
            <div className="flex align-items-center justify-content-between mb-2">
              <label className="font-semibold">Conditions (Rules)</label>
              <Button icon="pi pi-plus" size="small" rounded outlined onClick={addRule} tooltip="Add Rule" />
            </div>
            {rules.map((rule, idx) => (
              <div key={idx} className="flex gap-2 mb-2 align-items-center">
                <InputText value={rule.field} onChange={(e) => { const r = [...rules]; r[idx].field = e.target.value; setRules(r); }} placeholder="Field (e.g. amount)" className="flex-1" />
                <Dropdown value={rule.operator} options={OPERATORS} onChange={(e) => { const r = [...rules]; r[idx].operator = e.value; setRules(r); }} className="w-8rem" />
                <InputText value={rule.value} onChange={(e) => { const r = [...rules]; r[idx].value = e.target.value; setRules(r); }} placeholder="Value" className="flex-1" />
                <Dropdown value={rule.data_type} options={DATA_TYPES} onChange={(e) => { const r = [...rules]; r[idx].data_type = e.value; setRules(r); }} className="w-7rem" />
                <Button icon="pi pi-trash" rounded outlined severity="danger" size="small" onClick={() => removeRule(idx)} />
              </div>
            ))}
            {rules.length === 0 && <p className="text-600 text-sm m-0">No conditions — matrix will match all entities of this type</p>}
          </div>

          {/* Assignments */}
          <div>
            <div className="flex align-items-center justify-content-between mb-2">
              <label className="font-semibold">Approval Levels</label>
              <Button icon="pi pi-plus" size="small" rounded outlined onClick={addAssignment} tooltip="Add Level" />
            </div>
            {assignments.map((assign, idx) => (
              <div key={idx} className="flex gap-2 mb-2 align-items-center">
                <Tag value={`L${assign.level}`} severity="info" />
                <Dropdown value={assign.assignment_type} options={[{ label: 'Role', value: 'ROLE' }, { label: 'User', value: 'USER' }]} onChange={(e) => { const a = [...assignments]; a[idx].assignment_type = e.value; a[idx].user_ids = []; a[idx].role_ids = []; setAssignments(a); }} className="w-7rem" />
                {assign.assignment_type === 'ROLE' ? (
                  <MultiSelect
                    value={assign.role_ids}
                    options={roleOptions}
                    onChange={(e) => { const a = [...assignments]; a[idx].role_ids = e.value; setAssignments(a); }}
                    placeholder="Select roles"
                    display="chip"
                    filter
                    className="flex-1"
                  />
                ) : (
                  <MultiSelect
                    value={assign.user_ids}
                    options={userOptions}
                    onChange={(e) => { const a = [...assignments]; a[idx].user_ids = e.value; setAssignments(a); }}
                    placeholder="Select users"
                    display="chip"
                    filter
                    className="flex-1"
                  />
                )}
                <Button icon="pi pi-trash" rounded outlined severity="danger" size="small" onClick={() => removeAssignment(idx)} />
              </div>
            ))}
            {assignments.length === 0 && <p className="text-600 text-sm m-0">No approval levels defined</p>}
          </div>
        </div>
      </Dialog>
    </div>
  );
};
