/**
 * User data table component.
 * Displays users with employee details, column filters, and action buttons.
 */

import { useState } from 'react';
import { DataTable, type DataTableFilterMeta } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Tag } from 'primereact/tag';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { FilterMatchMode } from 'primereact/api';
import { apiClient } from '@shared/services/apiClient';
import { userApi } from '../api/userApi';
import type { User, UserRole } from '../models/User';
import type { TreeNode } from 'primereact/treenode';
import { Tree } from 'primereact/tree';

interface UserTableProps {
  users: User[];
  loading: boolean;
  onEdit: (user: User) => void;
}

interface UserDetail {
  employee_id: string | null;
  employee_name: string | null;
  first_name: string | null;
  middle_name: string | null;
  last_name: string | null;
  email: string | null;
  designation_title: string | null;
  department: string | null;
  business_unit: string | null;
  group_company: string | null;
  location: string | null;
  region: string | null;
  zone: string | null;
  grade: string | null;
  office_mobile_no: string | null;
  personal_mobile_no: string | null;
  date_of_joining: string | null;
  reporting_manager: string | null;
  direct_manager_name: string | null;
  direct_manager_email: string | null;
  sap_user_id: string | null;
  division_id: string | null;
  territory_id: string | null;
}

const defaultFilters: DataTableFilterMeta = {
  username: { value: null, matchMode: FilterMatchMode.CONTAINS },
  employee_id: { value: null, matchMode: FilterMatchMode.CONTAINS },
  employee_name: { value: null, matchMode: FilterMatchMode.CONTAINS },
  email: { value: null, matchMode: FilterMatchMode.CONTAINS },
};

export const UserTable = ({ users, loading, onEdit }: UserTableProps) => {
  const [filters, setFilters] = useState<DataTableFilterMeta>(defaultFilters);

  const formatDate = (dateStr: string | null): string => {
    if (!dateStr) return '—';
    const d = new Date(dateStr);
    const day = String(d.getDate()).padStart(2, '0');
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const year = d.getFullYear();
    let hours = d.getHours();
    const minutes = String(d.getMinutes()).padStart(2, '0');
    const seconds = String(d.getSeconds()).padStart(2, '0');
    const ampm = hours >= 12 ? 'PM' : 'AM';
    hours = hours % 12 || 12;
    return `${day}-${month}-${year} ${String(hours).padStart(2, '0')}:${minutes}:${seconds} ${ampm}`;
  };
  const [rolesDialogVisible, setRolesDialogVisible] = useState(false);
  const [rolesDialogUser, setRolesDialogUser] = useState('');
  const [rolesTreeData, setRolesTreeData] = useState<TreeNode[]>([]);
  const [rolesLoading, setRolesLoading] = useState(false);
  const [detailsDialogVisible, setDetailsDialogVisible] = useState(false);
  const [detailsUser, setDetailsUser] = useState<string>('');
  const [detailsData, setDetailsData] = useState<UserDetail | null>(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [historyDialogVisible, setHistoryDialogVisible] = useState(false);
  const [historyUser, setHistoryUser] = useState<string>('');
  const [historyData, setHistoryData] = useState<{ action: string; ip_address: string; user_agent: string; created_at: string }[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const statusBodyTemplate = (rowData: User) => {
    if (rowData.is_blocked) return <Tag value="Blocked" severity="danger" />;
    return rowData.is_active ? <Tag value="Active" severity="success" /> : <Tag value="Inactive" severity="warning" />;
  };

  const handleViewRoles = async (user: User) => {
    setRolesDialogUser(user.username);
    setRolesDialogVisible(true);
    setRolesLoading(true);
    try {
      const data = await userApi.getUserRoles(user.id);
      const treeNodes: TreeNode[] = data.roles.map((role: UserRole) => ({
        key: role.id,
        label: `${role.name} (${role.code})`,
        icon: 'pi pi-shield',
        children: role.permissions.map((perm) => ({
          key: `${role.id}-${perm.code}`,
          label: perm.name,
          icon: perm.scope === 'MENU' ? 'pi pi-bars' : perm.scope === 'API' ? 'pi pi-server' : 'pi pi-eye',
        })),
      }));
      setRolesTreeData(treeNodes);
    } catch {
      setRolesTreeData([{ key: 'error', label: 'Failed to load roles', icon: 'pi pi-exclamation-triangle' }]);
    } finally {
      setRolesLoading(false);
    }
  };

  const handleViewDetails = async (user: User) => {
    setDetailsUser(user.username);
    setDetailsDialogVisible(true);
    setDetailsLoading(true);
    try {
      const { data } = await apiClient.get<UserDetail>(`/users/${user.id}/details`);
      setDetailsData(data);
    } catch {
      setDetailsData(null);
    } finally {
      setDetailsLoading(false);
    }
  };

  const handleViewHistory = async (user: User) => {
    setHistoryUser(user.username);
    setHistoryDialogVisible(true);
    setHistoryLoading(true);
    try {
      const { data } = await apiClient.get<{ action: string; ip_address: string; user_agent: string; created_at: string }[]>(`/users/${user.id}/login-history`);
      setHistoryData(data);
    } catch {
      setHistoryData([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  const actionsBodyTemplate = (rowData: User) => (
    <div className="flex gap-1">
      <Button icon="pi pi-id-card" rounded outlined severity="secondary" size="small" onClick={() => handleViewDetails(rowData)} tooltip="Details" tooltipOptions={{ position: 'top' }} />
      <Button icon="pi pi-history" rounded outlined severity="help" size="small" onClick={() => handleViewHistory(rowData)} tooltip="Login History" tooltipOptions={{ position: 'top' }} />
      <Button icon="pi pi-shield" rounded outlined severity="warning" size="small" onClick={() => handleViewRoles(rowData)} tooltip="Roles" tooltipOptions={{ position: 'top' }} />
      <Button icon="pi pi-pencil" rounded outlined severity="info" size="small" onClick={() => onEdit(rowData)} tooltip="Edit" tooltipOptions={{ position: 'top' }} />
    </div>
  );

  return (
    <>
      <DataTable
        value={users}
        loading={loading}
        paginator
        rows={10}
        rowsPerPageOptions={[5, 10, 25, 50]}
        stripedRows
        showGridlines
        emptyMessage="No users found."
        filters={filters}
        filterDisplay="row"
        onFilter={(e) => setFilters(e.filters)}
        aria-label="Users table"
      >
        <Column field="username" header="Username" sortable filter filterPlaceholder="Search..." />
        <Column field="employee_id" header="Employee ID" sortable filter filterPlaceholder="Search..." />
        <Column field="employee_name" header="Employee Name" sortable filter filterPlaceholder="Search..." />
        <Column field="email" header="Email" sortable filter filterPlaceholder="Search..." />
        <Column header="Last Login" body={(row) => row.last_login ? formatDate(row.last_login) : '—'} sortable field="last_login" />
        <Column header="Status" body={statusBodyTemplate} style={{ width: '6rem' }} />
        <Column header="Actions" body={actionsBodyTemplate} style={{ width: '9rem' }} />
      </DataTable>

      {/* Roles Tree Dialog */}
      <Dialog header={`Roles — ${rolesDialogUser}`} visible={rolesDialogVisible} onHide={() => setRolesDialogVisible(false)} style={{ width: '550px' }} modal>
        {rolesLoading ? (
          <div className="flex align-items-center justify-content-center p-4"><i className="pi pi-spin pi-spinner text-2xl" /><span className="ml-2">Loading...</span></div>
        ) : rolesTreeData.length === 0 ? (
          <p className="text-600 p-3">No roles assigned.</p>
        ) : (
          <Tree value={rolesTreeData} className="w-full" />
        )}
      </Dialog>

      {/* User Details Dialog */}
      <Dialog header={`Employee Details — ${detailsUser}`} visible={detailsDialogVisible} onHide={() => setDetailsDialogVisible(false)} style={{ width: '650px' }} modal>
        {detailsLoading ? (
          <div className="flex align-items-center justify-content-center p-4"><i className="pi pi-spin pi-spinner text-2xl" /><span className="ml-2">Loading...</span></div>
        ) : !detailsData ? (
          <p className="text-600 p-3">No employee details available.</p>
        ) : (
          <div className="grid p-2" style={{ fontSize: '0.813rem' }}>
            {Object.entries(detailsData).filter(([key, v]) => v && !['id', 'is_active', 'is_blocked', 'is_validate_ad'].includes(key)).map(([key, value]) => (
              <div key={key} className="col-6 mb-2">
                <div className="text-600 text-xs uppercase">{key.replace(/_/g, ' ')}</div>
                <div className="text-900 font-medium">
                  {(key === 'created_date' || key === 'modified_date') ? formatDate(String(value)) : String(value)}
                </div>
              </div>
            ))}
          </div>
        )}
      </Dialog>

      {/* Login History Dialog */}
      <Dialog header={`Login History — ${historyUser}`} visible={historyDialogVisible} onHide={() => setHistoryDialogVisible(false)} style={{ width: '650px' }} modal>
        {historyLoading ? (
          <div className="flex align-items-center justify-content-center p-4"><i className="pi pi-spin pi-spinner text-2xl" /><span className="ml-2">Loading...</span></div>
        ) : historyData.length === 0 ? (
          <p className="text-600 p-3">No login history available.</p>
        ) : (
          <DataTable value={historyData} size="small" stripedRows paginator rows={10} emptyMessage="No history">
            <Column field="action" header="Action" body={(row) => <Tag value={row.action} severity={row.action === 'LOGIN_SUCCESS' ? 'success' : row.action === 'LOGOUT' ? 'info' : 'danger'} />} />
            <Column field="ip_address" header="IP Address" />
            <Column field="created_at" header="Time" body={(row) => formatDate(row.created_at)} />
          </DataTable>
        )}
      </Dialog>
    </>
  );
};
