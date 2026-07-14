/**
 * Manage Party page — Vendor master list with search, pagination, and actions.
 * Mirrors Firmway's "Manage Party" screen.
 * Wired to backend API via TanStack Query hooks.
 */

import { useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { DataTable, DataTablePageEvent } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { Menu } from 'primereact/menu';
import { Skeleton } from 'primereact/skeleton';
import { Message } from 'primereact/message';
import { useVendors, useExportVendors } from '../hooks/useVendors';
import { VendorResponse } from '../api/vendorApi';
import { AddPartyDialog } from '../components/AddPartyDialog';
import { ImportDialog } from '../components/ImportDialog';
import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';

const DEFAULT_PAGE_SIZE = 10;

/**
 * Generate and download the party import Excel template from the backend.
 */
const downloadTemplate = async () => {
  try {
    const { apiClient } = await import('@shared/services/apiClient');
    const { data } = await apiClient.get('/vlr/vendors/template', {
      responseType: 'blob',
    });
    const blob = new Blob([data], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'Party_Import_Template.xlsx';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  } catch (err) {
    console.error('Failed to download template', err);
  }
};

export const ManagePartyPage = () => {
  const navigate = useNavigate();
  const { companyCode } = useSelectedEntity();
  const [searchQuery, setSearchQuery] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [showImportDialog, setShowImportDialog] = useState(false);
  const moreActionsMenu = useRef<Menu>(null);

  const filters = appliedSearch ? { search: appliedSearch } : undefined;

  const {
    data: vendorData,
    isLoading,
    isError,
    error,
  } = useVendors(companyCode, filters, page, pageSize);

  const { triggerExport } = useExportVendors();

  const handleSearch = useCallback(() => {
    setAppliedSearch(searchQuery);
    setPage(1);
  }, [searchQuery]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        handleSearch();
      }
    },
    [handleSearch]
  );

  const handlePageChange = (event: DataTablePageEvent) => {
    setPage((event.page ?? 0) + 1);
    setPageSize(event.rows);
  };

  const handleExport = () => {
    triggerExport(companyCode, 'excel');
  };

  const moreActionsItems = [
    { label: 'Import', icon: 'pi pi-upload', command: () => setShowImportDialog(true) },
    { label: 'Export', icon: 'pi pi-download', command: handleExport },
    { label: 'Download template', icon: 'pi pi-file', command: downloadTemplate },
  ];

  const contactTemplate = (rowData: VendorResponse) => (
    <div>
      <span>{rowData.contacts?.[0]?.email ?? ''}</span>
      {rowData.contacts && rowData.contacts.length > 1 && (
        <span
          style={{
            marginLeft: 6,
            background: 'var(--color-primary-50)',
            color: 'var(--color-primary)',
            padding: '2px 6px',
            borderRadius: 'var(--radius-sm)',
            fontSize: '11px',
            fontWeight: 500,
          }}
        >
          +{rowData.contacts.length - 1}
        </span>
      )}
    </div>
  );

  const statusTemplate = (rowData: VendorResponse) => (
    <span className={`status-badge ${rowData.status.toLowerCase()}`}>
      {rowData.status}
    </span>
  );

  const actionTemplate = (rowData: VendorResponse) => (
    <span className="link-view" style={{ cursor: 'pointer' }} onClick={() => navigate(`/manage-party/${rowData.id}`)}>View</span>
  );

  // Loading skeleton
  if (isLoading) {
    return (
      <div>
        <div className="em-page-header">
          <h2>Manage Party</h2>
        </div>
        <div className="em-card" style={{ padding: '1rem' }}>
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} height="2.5rem" className="mb-2" />
          ))}
        </div>
      </div>
    );
  }

  // Error state
  if (isError) {
    return (
      <div>
        <div className="em-page-header">
          <h2>Manage Party</h2>
        </div>
        <div className="em-card">
          <Message
            severity="error"
            text={
              error instanceof Error
                ? error.message
                : 'Failed to load vendors. Please try again.'
            }
          />
        </div>
      </div>
    );
  }

  const vendors = vendorData?.items ?? [];
  const totalRecords = vendorData?.total ?? 0;

  return (
    <div>
      {/* Add Party Dialog */}
      <AddPartyDialog visible={showAddDialog} onHide={() => setShowAddDialog(false)} />

      {/* Import Dialog */}
      <ImportDialog visible={showImportDialog} onHide={() => setShowImportDialog(false)} />

      {/* Page Header */}
      <div className="em-page-header">
        <h2>Manage Party</h2>
        <div className="em-page-header-actions">
          <div className="em-search-bar">
            <InputText
              placeholder="Type and press enter to Search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              style={{ border: 'none', boxShadow: 'none', width: 200 }}
            />
            <i className="pi pi-search" style={{ cursor: 'pointer' }} onClick={handleSearch} />
          </div>
          <Button label="Add Party" icon="pi pi-plus" onClick={() => setShowAddDialog(true)} />
          <div>
            <Button
              label="More Actions"
              icon="pi pi-chevron-down"
              iconPos="right"
              className="p-button-outlined"
              onClick={(e) => moreActionsMenu.current?.toggle(e)}
            />
            <Menu model={moreActionsItems} popup ref={moreActionsMenu} />
          </div>
        </div>
      </div>

      {/* Data Table */}
      <div className="em-card" style={{ padding: 0 }}>
        <DataTable
          value={vendors}
          paginator
          lazy
          first={(page - 1) * pageSize}
          rows={pageSize}
          totalRecords={totalRecords}
          rowsPerPageOptions={[10, 25, 50]}
          onPage={handlePageChange}
          sortMode="multiple"
          emptyMessage="No vendors found."
          paginatorLeft={
            <div className="em-per-page">
              <span>{pageSize} per page</span>
            </div>
          }
        >
          <Column
            field="status"
            header="Party Type"
            body={() => 'Vendor'}
            sortable
            style={{ width: '10%' }}
          />
          <Column field="vendor_code" header="Party Code" sortable style={{ width: '12%' }} />
          <Column field="name" header="Party Name" sortable style={{ width: '25%' }} />
          <Column header="Contact Details" body={contactTemplate} sortable style={{ width: '25%' }} />
          <Column header="Status" body={statusTemplate} sortable style={{ width: '10%' }} />
          <Column header="Action" body={actionTemplate} style={{ width: '8%' }} />
        </DataTable>
      </div>
    </div>
  );
};
