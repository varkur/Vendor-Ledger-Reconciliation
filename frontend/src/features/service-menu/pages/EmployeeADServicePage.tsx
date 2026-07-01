/**
 * Employee AD Service verification page.
 * Allows users to test connectivity and all API endpoints of the Darwin AD service.
 */

import { useState, useRef } from 'react';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { Password } from 'primereact/password';
import { Toast } from 'primereact/toast';
import { Card } from 'primereact/card';
import { Tag } from 'primereact/tag';
import { Divider } from 'primereact/divider';
import { ProgressSpinner } from 'primereact/progressspinner';
import {
  useEmployeeADHealth,
  useValidateCredentials,
  useGetSelectedEmployees,
  useGetEmployees,
  useGetHierarchy,
} from '../hooks/useEmployeeAD';

export const EmployeeADServicePage = () => {
  const toast = useRef<Toast>(null);

  // Health check
  const { data: healthData, isLoading: healthLoading, refetch: refetchHealth } = useEmployeeADHealth();

  // Validate credentials form
  const [employeeId, setEmployeeId] = useState('');
  const [password, setPassword] = useState('');
  const validateMutation = useValidateCredentials();

  // Get selected employees form
  const [employeeIds, setEmployeeIds] = useState('');
  const getSelectedMutation = useGetSelectedEmployees();

  // Get all employees
  const getEmployeesMutation = useGetEmployees();

  // Get hierarchy
  const getHierarchyMutation = useGetHierarchy();

  const handleValidate = async () => {
    if (!employeeId.trim()) {
      toast.current?.show({ severity: 'warn', summary: 'Validation', detail: 'Employee ID is required', life: 3000 });
      return;
    }
    try {
      const result = await validateMutation.mutateAsync({
        employee_id: employeeId.trim(),
        password: password,
      });
      toast.current?.show({
        severity: result.is_valid_user ? 'success' : 'warn',
        summary: 'Credential Validation',
        detail: result.is_valid_user ? `Employee ${employeeId} is valid` : `Employee ${employeeId} validation failed`,
        life: 5000,
      });
    } catch (error: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: error.response?.data?.detail || 'Failed to validate', life: 5000 });
    }
  };

  const handleGetSelected = async () => {
    if (!employeeIds.trim()) {
      toast.current?.show({ severity: 'warn', summary: 'Validation', detail: 'Enter at least one Employee ID', life: 3000 });
      return;
    }
    const ids = employeeIds.split(',').map((id) => id.trim()).filter(Boolean);
    try {
      await getSelectedMutation.mutateAsync(ids);
      toast.current?.show({ severity: 'success', summary: 'Success', detail: 'Selected employees fetched', life: 3000 });
    } catch (error: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: error.response?.data?.detail || 'Failed to fetch', life: 5000 });
    }
  };

  const handleGetAllEmployees = async () => {
    try {
      await getEmployeesMutation.mutateAsync();
      toast.current?.show({ severity: 'success', summary: 'Success', detail: 'All employees fetched', life: 3000 });
    } catch (error: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: error.response?.data?.detail || 'Failed to fetch', life: 5000 });
    }
  };

  const handleGetHierarchy = async () => {
    try {
      await getHierarchyMutation.mutateAsync();
      toast.current?.show({ severity: 'success', summary: 'Success', detail: 'Hierarchy data fetched', life: 3000 });
    } catch (error: any) {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: error.response?.data?.detail || 'Failed to fetch', life: 5000 });
    }
  };

  const getStatusSeverity = (status: string | undefined) => {
    if (status === 'reachable') return 'success';
    if (status === 'unreachable') return 'danger';
    return 'info';
  };

  const renderJsonResponse = (data: unknown, label: string) => {
    if (!data) return null;
    return (
      <div className="mt-3 p-3 surface-100 border-round">
        <div className="flex align-items-center justify-content-between mb-2">
          <span className="font-semibold text-sm text-600">{label}</span>
          <Tag value="200 OK" severity="success" />
        </div>
        <pre className="text-xs overflow-auto m-0" style={{ maxHeight: '300px' }}>
          {JSON.stringify(data, null, 2)}
        </pre>
      </div>
    );
  };

  return (
    <div className="p-4">
      <Toast ref={toast} />

      {/* Header */}
      <div className="flex align-items-center justify-content-between mb-4">
        <div>
          <h2 className="text-2xl font-semibold text-900 m-0">Employee AD Service</h2>
          <p className="text-600 mt-1 mb-0">Verify and test the Darwin Active Directory integration endpoints</p>
        </div>
        <Tag
          value={healthData?.status === 'reachable' ? 'Online' : 'Offline'}
          severity={getStatusSeverity(healthData?.status)}
          icon={healthData?.status === 'reachable' ? 'pi pi-check-circle' : 'pi pi-times-circle'}
        />
      </div>

      {/* Service Health */}
      <Card title="Service Health" subTitle="Check connectivity to the Darwin AD service" className="mb-4">
        {healthLoading ? (
          <div className="flex align-items-center gap-2">
            <ProgressSpinner style={{ width: '24px', height: '24px' }} />
            <span>Checking service status...</span>
          </div>
        ) : (
          <div className="grid">
            <div className="col-12 md:col-8">
              <div className="flex flex-column gap-2">
                <div className="flex align-items-center gap-2">
                  <span className="font-semibold text-600" style={{ minWidth: '120px' }}>Service:</span>
                  <span>{healthData?.service || 'Employee AD (Darwin)'}</span>
                </div>
                <div className="flex align-items-center gap-2">
                  <span className="font-semibold text-600" style={{ minWidth: '120px' }}>Status:</span>
                  <Tag value={healthData?.status || 'unknown'} severity={getStatusSeverity(healthData?.status)} />
                </div>
                <div className="flex align-items-center gap-2">
                  <span className="font-semibold text-600" style={{ minWidth: '120px' }}>Configured:</span>
                  <Tag value={healthData?.configured ? 'Yes' : 'No'} severity={healthData?.configured ? 'success' : 'warning'} />
                </div>
                <div className="flex align-items-center gap-2">
                  <span className="font-semibold text-600" style={{ minWidth: '120px' }}>Base URL:</span>
                  <span className="text-sm" style={{ wordBreak: 'break-all' }}>{healthData?.base_url || '-'}</span>
                </div>
                {healthData?.status_code && (
                  <div className="flex align-items-center gap-2">
                    <span className="font-semibold text-600" style={{ minWidth: '120px' }}>HTTP Code:</span>
                    <span>{healthData.status_code}</span>
                  </div>
                )}
                {healthData?.error && (
                  <div className="flex align-items-center gap-2">
                    <span className="font-semibold text-600" style={{ minWidth: '120px' }}>Error:</span>
                    <span className="text-red-500 text-sm">{healthData.error}</span>
                  </div>
                )}
              </div>
            </div>
            <div className="col-12 md:col-4 flex align-items-end justify-content-end">
              <Button label="Refresh" icon="pi pi-refresh" severity="secondary" outlined onClick={() => refetchHealth()} aria-label="Refresh health" />
            </div>
          </div>
        )}
      </Card>

      <Divider />

      {/* Validate Credentials */}
      <Card title="POST /validatecredentials" subTitle="Validate employee AD credentials" className="mb-4">
        <div className="grid">
          <div className="col-12 md:col-4">
            <label htmlFor="emp-id" className="block font-medium mb-2">Employee ID</label>
            <InputText id="emp-id" value={employeeId} onChange={(e) => setEmployeeId(e.target.value)} placeholder="e.g. 93300040" className="w-full" />
          </div>
          <div className="col-12 md:col-4">
            <label htmlFor="emp-password" className="block font-medium mb-2">Password</label>
            <Password id="emp-password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter password" className="w-full" inputClassName="w-full" feedback={false} toggleMask />
          </div>
          <div className="col-12 md:col-4 flex align-items-end">
            <Button label="Validate" icon="pi pi-check" onClick={handleValidate} loading={validateMutation.isPending} />
          </div>
        </div>
        {validateMutation.data && (
          <div className="mt-3 p-3 surface-100 border-round">
            <div className="flex align-items-center gap-3 mb-2">
              <Tag value={validateMutation.data.is_valid_user ? 'Valid User' : 'Invalid User'} severity={validateMutation.data.is_valid_user ? 'success' : 'danger'} icon={validateMutation.data.is_valid_user ? 'pi pi-check' : 'pi pi-times'} />
              <Tag value={validateMutation.data.is_success ? 'Success' : 'Failed'} severity={validateMutation.data.is_success ? 'success' : 'danger'} />
            </div>
            <pre className="text-xs overflow-auto m-0" style={{ maxHeight: '200px' }}>
              {JSON.stringify(validateMutation.data.raw_response, null, 2)}
            </pre>
          </div>
        )}
      </Card>

      <Divider />

      {/* Get Selected Employees */}
      <Card title="POST /getselectedemployees" subTitle="Fetch employees by IDs (comma-separated)" className="mb-4">
        <div className="grid">
          <div className="col-12 md:col-8">
            <label htmlFor="emp-ids" className="block font-medium mb-2">Employee IDs</label>
            <InputText id="emp-ids" value={employeeIds} onChange={(e) => setEmployeeIds(e.target.value)} placeholder="e.g. 93300040, 93300041" className="w-full" />
          </div>
          <div className="col-12 md:col-4 flex align-items-end">
            <Button label="Fetch Selected" icon="pi pi-search" onClick={handleGetSelected} loading={getSelectedMutation.isPending} />
          </div>
        </div>
        {renderJsonResponse(getSelectedMutation.data, 'Response')}
      </Card>

      <Divider />

      {/* Get All Employees */}
      <Card title="GET /getemployees" subTitle="Fetch all employee records" className="mb-4">
        <Button label="Get All Employees" icon="pi pi-users" onClick={handleGetAllEmployees} loading={getEmployeesMutation.isPending} />
        {renderJsonResponse(getEmployeesMutation.data, 'Response')}
      </Card>

      <Divider />

      {/* Get Hierarchy */}
      <Card title="GET /getHierarchyData" subTitle="Fetch organizational hierarchy data" className="mb-4">
        <Button label="Get Hierarchy" icon="pi pi-sitemap" onClick={handleGetHierarchy} loading={getHierarchyMutation.isPending} />
        {renderJsonResponse(getHierarchyMutation.data, 'Response')}
      </Card>
    </div>
  );
};
