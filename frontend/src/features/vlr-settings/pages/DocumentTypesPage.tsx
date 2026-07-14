/**
 * Document Types Configuration page — manage document type classifications.
 * CRUD operations for document type mappings used in reconciliation.
 *
 * Requirements: 19 — Document Types Page
 */

import { useState, useRef } from 'react';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { Dropdown } from 'primereact/dropdown';
import { Checkbox } from 'primereact/checkbox';
import { Dialog } from 'primereact/dialog';
import { Toast } from 'primereact/toast';
import { Tag } from 'primereact/tag';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@shared/services/apiClient';
import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface DocumentType {
  id: string;
  document_type_code: string;
  category: string;
  is_tds: boolean;
  is_active: boolean;
}

interface DocumentTypeListResponse {
  items: DocumentType[];
  total: number;
  page: number;
  page_size: number;
}

interface DocumentTypeFormData {
  document_type_code: string;
  category: string;
  is_tds: boolean;
  is_active: boolean;
}

type FormErrors = Partial<Record<keyof DocumentTypeFormData, string>>;

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const CATEGORY_OPTIONS = [
  { label: 'Invoice', value: 'Invoice' },
  { label: 'Payment', value: 'Payment' },
  { label: 'Credit Note', value: 'Credit Note' },
  { label: 'Debit Note', value: 'Debit Note' },
  { label: 'TDS', value: 'TDS' },
  { label: 'Other', value: 'Other' },
];

// ─────────────────────────────────────────────────────────────────────────────
// API
// ─────────────────────────────────────────────────────────────────────────────

async function getDocumentTypes(
  companyCode: string
): Promise<DocumentTypeListResponse> {
  const { data } = await apiClient.get<DocumentTypeListResponse>('/vlr/settings/document-types', {
    params: { company_code: companyCode },
  });
  return data;
}

async function createDocumentType(
  companyCode: string,
  payload: DocumentTypeFormData
): Promise<DocumentType> {
  const { data } = await apiClient.post<DocumentType>('/vlr/settings/document-types', {
    ...payload,
    company_code: companyCode,
  });
  return data;
}

async function updateDocumentType(
  companyCode: string,
  id: string,
  payload: DocumentTypeFormData
): Promise<DocumentType> {
  const { data } = await apiClient.put<DocumentType>(`/vlr/settings/document-types/${id}`, {
    ...payload,
    company_code: companyCode,
  });
  return data;
}

async function deleteDocumentType(
  companyCode: string,
  id: string
): Promise<void> {
  await apiClient.delete(`/vlr/settings/document-types/${id}`, {
    params: { company_code: companyCode },
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export const DocumentTypesPage = () => {
  const { companyCode } = useSelectedEntity();
  const queryClient = useQueryClient();
  const toast = useRef<Toast>(null);

  // Dialog state
  const [dialogVisible, setDialogVisible] = useState(false);
  const [dialogMode, setDialogMode] = useState<'create' | 'edit'>('create');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState<string | null>(null);

  // Form state
  const [formData, setFormData] = useState<DocumentTypeFormData>({
    document_type_code: '',
    category: '',
    is_tds: false,
    is_active: true,
  });
  const [formErrors, setFormErrors] = useState<FormErrors>({});

  // Delete confirmation dialog
  const [deleteDialogVisible, setDeleteDialogVisible] = useState(false);
  const [deletingItem, setDeletingItem] = useState<DocumentType | null>(null);

  // ─── Query ───────────────────────────────────────────────────────────────

  const documentTypesQuery = useQuery<DocumentTypeListResponse, Error>({
    queryKey: ['document-types', companyCode],
    queryFn: () => getDocumentTypes(companyCode),
    enabled: !!companyCode,
    retry: 2,
    staleTime: 30_000,
  });

  // ─── Form Validation ─────────────────────────────────────────────────────

  const validateForm = (): boolean => {
    const errors: FormErrors = {};
    if (!formData.document_type_code.trim()) {
      errors.document_type_code = 'Code is required.';
    }
    if (!formData.category) {
      errors.category = 'Category is required.';
    }
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  // ─── Handlers ────────────────────────────────────────────────────────────

  const handleOpenCreate = () => {
    setFormData({
      document_type_code: '',
      category: '',
      is_tds: false,
      is_active: true,
    });
    setFormErrors({});
    setDialogMode('create');
    setEditingId(null);
    setDialogVisible(true);
  };

  const handleOpenEdit = (item: DocumentType) => {
    setFormData({
      document_type_code: item.document_type_code,
      category: item.category,
      is_tds: item.is_tds,
      is_active: item.is_active,
    });
    setFormErrors({});
    setDialogMode('edit');
    setEditingId(item.id);
    setDialogVisible(true);
  };

  const handleSubmit = async () => {
    if (!validateForm()) return;
    setIsSaving(true);
    setFormErrors({});

    try {
      if (dialogMode === 'create') {
        await createDocumentType(companyCode, formData);
        toast.current?.show({
          severity: 'success',
          summary: 'Document Type Created',
          detail: 'Document type created successfully.',
        });
      } else {
        await updateDocumentType(companyCode, editingId!, formData);
        toast.current?.show({
          severity: 'success',
          summary: 'Document Type Updated',
          detail: 'Document type updated successfully.',
        });
      }
      setDialogVisible(false);
      queryClient.invalidateQueries({ queryKey: ['document-types'] });
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      if (typeof detail === 'string') {
        setFormErrors({ document_type_code: detail });
      } else if (Array.isArray(detail)) {
        const fieldErrors: FormErrors = {};
        detail.forEach((e: any) => {
          const field = e.loc?.[e.loc.length - 1] as keyof DocumentTypeFormData | undefined;
          if (field && field in formData) {
            fieldErrors[field] = e.msg;
          }
        });
        setFormErrors(Object.keys(fieldErrors).length > 0 ? fieldErrors : { document_type_code: 'Failed to save document type.' });
      } else {
        toast.current?.show({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to save document type. Please try again.',
        });
      }
    } finally {
      setIsSaving(false);
    }
  };

  const handleConfirmDelete = (item: DocumentType) => {
    setDeletingItem(item);
    setDeleteDialogVisible(true);
  };

  const handleDelete = async () => {
    if (!deletingItem) return;
    setIsDeleting(deletingItem.id);
    try {
      await deleteDocumentType(companyCode, deletingItem.id);
      toast.current?.show({
        severity: 'success',
        summary: 'Document Type Deleted',
        detail: `Document type "${deletingItem.document_type_code}" deleted successfully.`,
      });
      queryClient.invalidateQueries({ queryKey: ['document-types'] });
    } catch (err: any) {
      toast.current?.show({
        severity: 'error',
        summary: 'Delete Failed',
        detail: err.response?.data?.detail || 'Failed to delete document type.',
      });
    } finally {
      setIsDeleting(null);
      setDeleteDialogVisible(false);
      setDeletingItem(null);
    }
  };

  // ─── Column Templates ────────────────────────────────────────────────────

  const isTdsTemplate = (rowData: DocumentType) => (
    <Tag
      value={rowData.is_tds ? 'Yes' : 'No'}
      severity={rowData.is_tds ? 'info' : 'warning'}
    />
  );

  const isActiveTemplate = (rowData: DocumentType) => (
    <Tag
      value={rowData.is_active ? 'Active' : 'Inactive'}
      severity={rowData.is_active ? 'success' : 'danger'}
    />
  );

  const actionsTemplate = (rowData: DocumentType) => (
    <div className="flex gap-1">
      <Button
        icon="pi pi-pencil"
        className="p-button-text p-button-sm"
        tooltip="Edit"
        tooltipOptions={{ position: 'top' }}
        onClick={() => handleOpenEdit(rowData)}
      />
      <Button
        icon="pi pi-trash"
        className="p-button-text p-button-sm p-button-danger"
        tooltip="Delete"
        tooltipOptions={{ position: 'top' }}
        onClick={() => handleConfirmDelete(rowData)}
        loading={isDeleting === rowData.id}
      />
    </div>
  );

  // ─── Render ──────────────────────────────────────────────────────────────

  const renderContent = () => {
    if (documentTypesQuery.isLoading) {
      return (
        <div className="flex justify-content-center align-items-center" style={{ minHeight: 300 }}>
          <ProgressSpinner style={{ width: '50px', height: '50px' }} />
        </div>
      );
    }

    if (documentTypesQuery.isError) {
      return (
        <div className="flex flex-column align-items-center gap-3" style={{ padding: '2rem' }}>
          <Message severity="error" text={documentTypesQuery.error?.message || 'Failed to load document types.'} />
          <Button label="Retry" icon="pi pi-refresh" onClick={() => documentTypesQuery.refetch()} />
        </div>
      );
    }

    const data = documentTypesQuery.data;

    if (!data?.items?.length) {
      return (
        <>
          <div className="em-page-header">
            <h2>Document Types</h2>
            <div className="em-page-header-actions">
              <Button label="Create" icon="pi pi-plus" onClick={handleOpenCreate} />
            </div>
          </div>
          <div className="em-card">
            <div className="flex flex-column align-items-center gap-3 py-6">
              <i className="pi pi-file text-4xl text-color-secondary" />
              <p className="text-color-secondary">No document types configured. Click "Create" to add one.</p>
            </div>
          </div>
        </>
      );
    }

    return (
      <>
        {/* Header */}
        <div className="em-page-header">
          <h2>Document Types</h2>
          <div className="em-page-header-actions">
            <Button label="Create" icon="pi pi-plus" onClick={handleOpenCreate} />
          </div>
        </div>

        {/* Table */}
        <div className="em-card">
          <DataTable value={data.items} responsiveLayout="scroll" emptyMessage="No document types found.">
            <Column field="document_type_code" header="Code" sortable />
            <Column field="category" header="Category" sortable />
            <Column header="Is TDS" body={isTdsTemplate} style={{ width: '100px' }} />
            <Column header="Active" body={isActiveTemplate} style={{ width: '100px' }} />
            <Column header="Actions" body={actionsTemplate} style={{ width: '120px' }} />
          </DataTable>
        </div>
      </>
    );
  };

  // ─── Create/Edit Dialog ──────────────────────────────────────────────────

  const renderFormDialog = () => (
    <Dialog
      header={dialogMode === 'create' ? 'Create Document Type' : 'Edit Document Type'}
      visible={dialogVisible}
      style={{ width: '450px' }}
      onHide={() => setDialogVisible(false)}
      modal
    >
      <div className="flex flex-column gap-3">
        <div>
          <label htmlFor="doc-type-code" className="font-bold text-sm block mb-1">
            Code *
          </label>
          <InputText
            id="doc-type-code"
            value={formData.document_type_code}
            onChange={(e) => setFormData({ ...formData, document_type_code: e.target.value })}
            className={`w-full ${formErrors.document_type_code ? 'p-invalid' : ''}`}
            placeholder="Enter document type code"
            disabled={dialogMode === 'edit'}
          />
          {formErrors.document_type_code && (
            <small className="p-error block mt-1">{formErrors.document_type_code}</small>
          )}
        </div>
        <div>
          <label htmlFor="doc-type-category" className="font-bold text-sm block mb-1">
            Category *
          </label>
          <Dropdown
            id="doc-type-category"
            value={formData.category}
            options={CATEGORY_OPTIONS}
            onChange={(e) => setFormData({ ...formData, category: e.value })}
            className={`w-full ${formErrors.category ? 'p-invalid' : ''}`}
            placeholder="Select a category"
          />
          {formErrors.category && (
            <small className="p-error block mt-1">{formErrors.category}</small>
          )}
        </div>
        <div className="flex align-items-center gap-2">
          <Checkbox
            inputId="doc-type-is-tds"
            checked={formData.is_tds}
            onChange={(e) => setFormData({ ...formData, is_tds: e.checked ?? false })}
          />
          <label htmlFor="doc-type-is-tds" className="text-sm">
            Is TDS
          </label>
        </div>
        <div className="flex align-items-center gap-2">
          <Checkbox
            inputId="doc-type-is-active"
            checked={formData.is_active}
            onChange={(e) => setFormData({ ...formData, is_active: e.checked ?? false })}
          />
          <label htmlFor="doc-type-is-active" className="text-sm">
            Active
          </label>
        </div>
        <div className="flex justify-content-end gap-2 pt-2">
          <Button
            label="Cancel"
            className="p-button-text"
            onClick={() => setDialogVisible(false)}
            disabled={isSaving}
          />
          <Button
            label={dialogMode === 'create' ? 'Create' : 'Save'}
            icon={dialogMode === 'create' ? 'pi pi-plus' : 'pi pi-save'}
            onClick={handleSubmit}
            loading={isSaving}
          />
        </div>
      </div>
    </Dialog>
  );

  // ─── Delete Confirmation Dialog ──────────────────────────────────────────

  const renderDeleteDialog = () => (
    <Dialog
      header="Confirm Delete"
      visible={deleteDialogVisible}
      style={{ width: '400px' }}
      onHide={() => { setDeleteDialogVisible(false); setDeletingItem(null); }}
      modal
    >
      <div className="flex flex-column gap-3">
        <p>
          Are you sure you want to delete document type <strong>{deletingItem?.document_type_code}</strong>?
        </p>
        <div className="flex justify-content-end gap-2">
          <Button
            label="Cancel"
            className="p-button-text"
            onClick={() => { setDeleteDialogVisible(false); setDeletingItem(null); }}
          />
          <Button
            label="Delete"
            icon="pi pi-trash"
            className="p-button-danger"
            onClick={handleDelete}
            loading={isDeleting !== null}
          />
        </div>
      </div>
    </Dialog>
  );

  return (
    <div>
      <Toast ref={toast} />
      {renderContent()}
      {renderFormDialog()}
      {renderDeleteDialog()}
    </div>
  );
};
