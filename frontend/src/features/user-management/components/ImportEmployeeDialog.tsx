/**
 * Import Employee Dialog.
 * Fetches employees from Darwin AD by IDs and upserts them into the system.
 */

import { useState } from 'react';
import { InputText } from 'primereact/inputtext';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Tag } from 'primereact/tag';
import { useImportEmployees } from '../hooks/useUsers';
import type { ImportResult } from '../models/User';

interface ImportEmployeeDialogProps {
  visible: boolean;
  onHide: () => void;
  onSuccess?: () => void;
}

export const ImportEmployeeDialog = ({ visible, onHide, onSuccess }: ImportEmployeeDialogProps) => {
  const [employeeIds, setEmployeeIds] = useState('');
  const [results, setResults] = useState<ImportResult[] | null>(null);
  const importMutation = useImportEmployees();

  const handleImport = async () => {
    const ids = employeeIds
      .split(',')
      .map((id) => id.trim())
      .filter(Boolean);

    if (ids.length === 0) return;

    try {
      const response = await importMutation.mutateAsync(ids);
      setResults(response.results);
      if (response.created > 0 || response.updated > 0) {
        onSuccess?.();
      }
    } catch {
      // Error handled via toast in parent
    }
  };

  const handleClose = () => {
    setEmployeeIds('');
    setResults(null);
    onHide();
  };

  const statusTemplate = (row: ImportResult) => {
    const severityMap: Record<string, 'success' | 'info' | 'danger'> = {
      created: 'success',
      updated: 'info',
      failed: 'danger',
    };
    return <Tag value={row.status} severity={severityMap[row.status] || 'info'} />;
  };

  const footer = (
    <div className="flex justify-content-end gap-2">
      <Button
        label="Close"
        icon="pi pi-times"
        severity="secondary"
        outlined
        onClick={handleClose}
      />
      {!results && (
        <Button
          label="Import"
          icon="pi pi-download"
          onClick={handleImport}
          loading={importMutation.isPending}
          disabled={!employeeIds.trim()}
        />
      )}
    </div>
  );

  return (
    <Dialog
      header="Fetch & Import Employees"
      visible={visible}
      onHide={handleClose}
      style={{ width: '600px' }}
      footer={footer}
      modal
      aria-label="Import employees dialog"
    >
      <div className="flex flex-column gap-4 pt-2">
        {/* Input */}
        <div className="flex flex-column gap-2">
          <label htmlFor="import-ids" className="font-medium">
            Employee IDs (comma-separated)
          </label>
          <InputText
            id="import-ids"
            value={employeeIds}
            onChange={(e) => setEmployeeIds(e.target.value)}
            placeholder="e.g. 93300040, 93300041, 93300042"
            className="w-full"
            disabled={!!results}
            aria-label="Employee IDs to import"
          />
          <small className="text-600">
            Employees will be imported with username = Employee ID, default password = Employee ID, role = USER
          </small>
        </div>

        {/* Results table */}
        {results && (
          <div>
            <div className="flex align-items-center gap-3 mb-3">
              <Tag value={`Created: ${importMutation.data?.created || 0}`} severity="success" />
              <Tag value={`Updated: ${importMutation.data?.updated || 0}`} severity="info" />
              <Tag value={`Failed: ${importMutation.data?.failed || 0}`} severity="danger" />
            </div>
            <DataTable
              value={results}
              size="small"
              stripedRows
              paginator={results.length > 5}
              rows={5}
              emptyMessage="No results"
              aria-label="Import results"
            >
              <Column field="employee_id" header="Employee ID" />
              <Column header="Status" body={statusTemplate} />
              <Column field="message" header="Message" />
            </DataTable>
          </div>
        )}
      </div>
    </Dialog>
  );
};
