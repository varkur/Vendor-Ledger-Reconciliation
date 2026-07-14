/**
 * Email Templates Page — Full-featured template management for VLR email workflows.
 * List view: Table of templates with category filter tabs.
 * Editor view: Form with placeholder insertion, attachment config, and toggles.
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { Dropdown } from 'primereact/dropdown';
import { InputSwitch } from 'primereact/inputswitch';
import { Checkbox } from 'primereact/checkbox';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';
import { ConfirmDialog, confirmDialog } from 'primereact/confirmdialog';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@shared/services/apiClient';
import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';

// ─── Types ─────────────────────────────────────────────────────────────────────

interface AttachmentConfig {
  include_pdf_ledger: boolean;
  include_excel_statement: boolean;
  include_custom_attachments: boolean;
  custom_attachment_note: string;
}

interface EmailTemplate {
  id: string;
  name: string;
  subject: string;
  body: string;
  category: string;
  include_portal_link: boolean;
  include_letterhead: boolean;
  attachments: AttachmentConfig;
  placeholders_used: string[];
  created_by: string;
  is_default: boolean;
}

interface EmailTemplateListResponse {
  items: EmailTemplate[];
  total: number;
  page: number;
  page_size: number;
}

interface TemplateFormData {
  name: string;
  subject: string;
  body: string;
  category: string;
  include_portal_link: boolean;
  include_letterhead: boolean;
  attachments: AttachmentConfig;
}

// ─── API Functions ─────────────────────────────────────────────────────────────

const BASE = '/vlr/email-templates';

async function listTemplates(
  companyCode: string,
  page: number,
  pageSize: number,
  category?: string,
  search?: string
): Promise<EmailTemplateListResponse> {
  const { data } = await apiClient.get(BASE, {
    params: {
      company_code: companyCode,
      page,
      page_size: pageSize,
      category: category || undefined,
      search: search || undefined,
    },
  });
  return data;
}

async function createTemplate(companyCode: string, payload: TemplateFormData): Promise<EmailTemplate> {
  const { data } = await apiClient.post(BASE, payload, { params: { company_code: companyCode } });
  return data;
}

async function updateTemplate(
  companyCode: string,
  id: string,
  payload: Partial<TemplateFormData>
): Promise<EmailTemplate> {
  const { data } = await apiClient.put(`${BASE}/${id}`, payload, {
    params: { company_code: companyCode },
  });
  return data;
}

async function deleteTemplate(companyCode: string, id: string): Promise<void> {
  await apiClient.delete(`${BASE}/${id}`, { params: { company_code: companyCode } });
}

// ─── Constants ─────────────────────────────────────────────────────────────────

const AVAILABLE_PLACEHOLDERS = [
  'vendor_name',
  'vendor_code',
  'company_name',
  'portal_link',
  'period_start',
  'period_end',
  'due_date',
  'contact_person',
  'sender_name',
  'sender_email',
  'case_id',
  'fiscal_year',
  'reminder_count',
  'branch_name',
];

const CATEGORY_OPTIONS = [
  { label: 'General', value: 'general' },
  { label: 'Ledger Request', value: 'ledger_request' },
  { label: 'Reminder', value: 'reminder' },
  { label: 'Escalation', value: 'escalation' },
];

const CATEGORY_TABS = [
  { label: 'All', value: '' },
  { label: 'Ledger Request', value: 'ledger_request' },
  { label: 'Reminder', value: 'reminder' },
  { label: 'Escalation', value: 'escalation' },
  { label: 'General', value: 'general' },
];

const CATEGORY_SEVERITY_MAP: Record<string, 'success' | 'info' | 'warning' | 'danger'> = {
  ledger_request: 'info',
  reminder: 'warning',
  escalation: 'danger',
  general: 'success',
};

const EMPTY_FORM: TemplateFormData = {
  name: '',
  subject: '',
  body: '',
  category: 'general',
  include_portal_link: true,
  include_letterhead: false,
  attachments: {
    include_pdf_ledger: false,
    include_excel_statement: false,
    include_custom_attachments: false,
    custom_attachment_note: '',
  },
};

// ─── Component ─────────────────────────────────────────────────────────────────

export const EmailTemplatesPage = () => {
  const { companyCode } = useSelectedEntity();
  const queryClient = useQueryClient();
  const toast = useRef<Toast>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const subjectRef = useRef<HTMLInputElement>(null);

  // State
  const [view, setView] = useState<'list' | 'editor'>('list');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<TemplateFormData>({ ...EMPTY_FORM });
  const [categoryFilter, setCategoryFilter] = useState('');
  const [searchText, setSearchText] = useState('');
  const [page, setPage] = useState(1);
  const [saving, setSaving] = useState(false);
  const [insertTarget, setInsertTarget] = useState<'subject' | 'body'>('body');

  // Query
  const {
    data: templatesData,
    isLoading,
    isError,
    error,
  } = useQuery<EmailTemplateListResponse>({
    queryKey: ['email-templates', companyCode, page, categoryFilter, searchText],
    queryFn: () => listTemplates(companyCode, page, 50, categoryFilter || undefined, searchText || undefined),
    enabled: !!companyCode,
    staleTime: 30_000,
  });

  // Reset page on filter changes
  useEffect(() => {
    setPage(1);
  }, [categoryFilter, searchText]);

  // ─── Handlers ──────────────────────────────────────────────────────────────

  const handleNew = useCallback(() => {
    setEditingId(null);
    setForm({ ...EMPTY_FORM });
    setView('editor');
  }, []);

  const handleEdit = useCallback((template: EmailTemplate) => {
    setEditingId(template.id);
    setForm({
      name: template.name,
      subject: template.subject,
      body: template.body,
      category: template.category,
      include_portal_link: template.include_portal_link,
      include_letterhead: template.include_letterhead,
      attachments: { ...template.attachments },
    });
    setView('editor');
  }, []);

  const handleDelete = useCallback(
    (template: EmailTemplate) => {
      confirmDialog({
        message: `Are you sure you want to delete "${template.name}"?`,
        header: 'Delete Template',
        icon: 'pi pi-exclamation-triangle',
        acceptClassName: 'p-button-danger',
        accept: async () => {
          try {
            await deleteTemplate(companyCode, template.id);
            toast.current?.show({ severity: 'success', summary: 'Deleted', detail: 'Template deleted successfully.' });
            queryClient.invalidateQueries({ queryKey: ['email-templates'] });
          } catch {
            toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to delete template.' });
          }
        },
      });
    },
    [companyCode, queryClient]
  );

  const handleSave = useCallback(async () => {
    if (!form.name.trim() || !form.subject.trim() || !form.body.trim()) {
      toast.current?.show({ severity: 'warn', summary: 'Validation', detail: 'Name, Subject, and Body are required.' });
      return;
    }

    setSaving(true);
    try {
      if (editingId) {
        await updateTemplate(companyCode, editingId, form);
        toast.current?.show({ severity: 'success', summary: 'Updated', detail: 'Template updated successfully.' });
      } else {
        await createTemplate(companyCode, form);
        toast.current?.show({ severity: 'success', summary: 'Created', detail: 'Template created successfully.' });
      }
      queryClient.invalidateQueries({ queryKey: ['email-templates'] });
      setView('list');
    } catch {
      toast.current?.show({ severity: 'error', summary: 'Error', detail: 'Failed to save template.' });
    } finally {
      setSaving(false);
    }
  }, [form, editingId, companyCode, queryClient]);

  const handleCancel = useCallback(() => {
    setView('list');
    setEditingId(null);
    setForm({ ...EMPTY_FORM });
  }, []);

  const insertPlaceholder = useCallback(
    (placeholder: string) => {
      const tag = `{{${placeholder}}}`;
      if (insertTarget === 'body' && bodyRef.current) {
        const el = bodyRef.current;
        const start = el.selectionStart ?? el.value.length;
        const end = el.selectionEnd ?? el.value.length;
        const newValue = el.value.substring(0, start) + tag + el.value.substring(end);
        setForm((prev) => ({ ...prev, body: newValue }));
        // Restore cursor position after React re-render
        setTimeout(() => {
          el.focus();
          el.setSelectionRange(start + tag.length, start + tag.length);
        }, 0);
      } else if (insertTarget === 'subject' && subjectRef.current) {
        const el = subjectRef.current;
        const start = el.selectionStart ?? el.value.length;
        const end = el.selectionEnd ?? el.value.length;
        const newValue = el.value.substring(0, start) + tag + el.value.substring(end);
        setForm((prev) => ({ ...prev, subject: newValue }));
        setTimeout(() => {
          el.focus();
          el.setSelectionRange(start + tag.length, start + tag.length);
        }, 0);
      }
    },
    [insertTarget]
  );

  // ─── List View Column Templates ────────────────────────────────────────────

  const categoryBodyTemplate = (row: EmailTemplate) => {
    const severity = CATEGORY_SEVERITY_MAP[row.category] || 'info';
    const label = CATEGORY_OPTIONS.find((c) => c.value === row.category)?.label || row.category;
    return <Tag value={label} severity={severity} />;
  };

  const portalLinkBodyTemplate = (row: EmailTemplate) => {
    return row.include_portal_link ? (
      <i className="pi pi-check-circle" style={{ color: 'var(--green-500)', fontSize: '1.1rem' }} />
    ) : (
      <i className="pi pi-minus-circle" style={{ color: 'var(--color-text-muted)', fontSize: '1.1rem' }} />
    );
  };

  const attachmentsBodyTemplate = (row: EmailTemplate) => {
    let count = 0;
    if (row.attachments.include_pdf_ledger) count++;
    if (row.attachments.include_excel_statement) count++;
    if (row.attachments.include_custom_attachments) count++;
    return count > 0 ? (
      <span className="flex align-items-center gap-1">
        <i className="pi pi-paperclip" /> {count}
      </span>
    ) : (
      <span style={{ color: 'var(--color-text-muted)' }}>—</span>
    );
  };

  const actionsBodyTemplate = (row: EmailTemplate) => {
    return (
      <div className="flex gap-2">
        <Button
          icon="pi pi-pencil"
          className="p-button-text p-button-sm"
          tooltip="Edit"
          tooltipOptions={{ position: 'top' }}
          onClick={() => handleEdit(row)}
          aria-label={`Edit template ${row.name}`}
        />
        <Button
          icon="pi pi-trash"
          className="p-button-text p-button-danger p-button-sm"
          tooltip="Delete"
          tooltipOptions={{ position: 'top' }}
          onClick={() => handleDelete(row)}
          disabled={row.is_default}
          aria-label={`Delete template ${row.name}`}
        />
      </div>
    );
  };

  // ─── Render ────────────────────────────────────────────────────────────────

  return (
    <div>
      <Toast ref={toast} />
      <ConfirmDialog />

      <div className="flex align-items-center justify-content-between mb-4">
        <h2 className="m-0">Email Templates</h2>
        {view === 'list' && (
          <Button label="New Template" icon="pi pi-plus" onClick={handleNew} />
        )}
      </div>

      {view === 'list' && (
        <>
          {/* Category Filter Tabs */}
          <div className="flex gap-2 mb-3 flex-wrap">
            {CATEGORY_TABS.map((tab) => (
              <Button
                key={tab.value}
                label={tab.label}
                className={categoryFilter === tab.value ? '' : 'p-button-outlined'}
                size="small"
                onClick={() => setCategoryFilter(tab.value)}
              />
            ))}
            <span className="flex-1" />
            <span className="p-input-icon-left">
              <i className="pi pi-search" />
              <InputText
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                placeholder="Search templates..."
                style={{ width: 220 }}
              />
            </span>
          </div>

          {/* Loading */}
          {isLoading && (
            <div className="flex justify-content-center p-5">
              <ProgressSpinner style={{ width: '40px', height: '40px' }} />
            </div>
          )}

          {/* Error */}
          {isError && (
            <Message
              severity="error"
              text={error?.message ?? 'Failed to load templates.'}
              className="w-full mb-3"
            />
          )}

          {/* Table */}
          {!isLoading && templatesData && (
            <DataTable
              value={templatesData.items}
              paginator
              rows={20}
              totalRecords={templatesData.total}
              lazy={false}
              emptyMessage="No templates found."
              stripedRows
              size="small"
              responsiveLayout="scroll"
            >
              <Column field="name" header="Name" sortable style={{ minWidth: '200px' }} />
              <Column header="Category" body={categoryBodyTemplate} style={{ width: '140px' }} />
              <Column header="Portal Link" body={portalLinkBodyTemplate} style={{ width: '100px', textAlign: 'center' }} />
              <Column header="Attachments" body={attachmentsBodyTemplate} style={{ width: '110px' }} />
              <Column field="created_by" header="Created By" style={{ width: '120px' }} />
              <Column header="Actions" body={actionsBodyTemplate} style={{ width: '100px' }} />
            </DataTable>
          )}
        </>
      )}

      {view === 'editor' && (
        <div className="grid">
          {/* Form Column */}
          <div className="col-12 lg:col-8">
            <div className="em-form-section">
              <div className="em-form-section-title">
                {editingId ? 'Edit Template' : 'New Template'}
              </div>

              {/* Template Name */}
              <div className="mb-3">
                <label className="block mb-2 font-medium text-sm">Template Name*</label>
                <InputText
                  value={form.name}
                  onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
                  placeholder="e.g. Ledger Request - Standard"
                  className="w-full"
                />
              </div>

              {/* Category */}
              <div className="mb-3">
                <label className="block mb-2 font-medium text-sm">Category*</label>
                <Dropdown
                  value={form.category}
                  options={CATEGORY_OPTIONS}
                  onChange={(e) => setForm((prev) => ({ ...prev, category: e.value }))}
                  className="w-full"
                  placeholder="Select category"
                />
              </div>

              {/* Subject */}
              <div className="mb-3">
                <label className="block mb-2 font-medium text-sm">Subject Line*</label>
                <InputText
                  ref={subjectRef}
                  value={form.subject}
                  onChange={(e) => setForm((prev) => ({ ...prev, subject: e.target.value }))}
                  placeholder="e.g. Ledger Confirmation - {{company_name}}"
                  className="w-full"
                  onFocus={() => setInsertTarget('subject')}
                />
              </div>

              {/* Placeholder Chips */}
              <div className="mb-2">
                <label className="block mb-2 font-medium text-sm">
                  Insert Placeholder (click to insert at cursor)
                </label>
                <div className="flex flex-wrap gap-2">
                  {AVAILABLE_PLACEHOLDERS.map((p) => (
                    <Tag
                      key={p}
                      value={`{{${p}}}`}
                      style={{ cursor: 'pointer', fontSize: '0.75rem' }}
                      severity="info"
                      onClick={() => insertPlaceholder(p)}
                    />
                  ))}
                </div>
              </div>

              {/* Body */}
              <div className="mb-3">
                <label className="block mb-2 font-medium text-sm">Email Body*</label>
                <InputTextarea
                  ref={bodyRef}
                  value={form.body}
                  onChange={(e) => setForm((prev) => ({ ...prev, body: e.target.value }))}
                  placeholder="Compose your email body here..."
                  className="w-full"
                  rows={14}
                  autoResize
                  onFocus={() => setInsertTarget('body')}
                />
              </div>

              {/* Toggles */}
              <div className="grid mb-3">
                <div className="col-12 md:col-6">
                  <div className="flex align-items-center gap-3">
                    <InputSwitch
                      checked={form.include_portal_link}
                      onChange={(e) =>
                        setForm((prev) => ({ ...prev, include_portal_link: e.value ?? false }))
                      }
                    />
                    <label className="font-medium text-sm">Include Portal Link</label>
                  </div>
                </div>
                <div className="col-12 md:col-6">
                  <div className="flex align-items-center gap-3">
                    <InputSwitch
                      checked={form.include_letterhead}
                      onChange={(e) =>
                        setForm((prev) => ({ ...prev, include_letterhead: e.value ?? false }))
                      }
                    />
                    <label className="font-medium text-sm">Include Letterhead</label>
                  </div>
                </div>
              </div>

              {/* Attachment Config */}
              <div className="em-form-section-title">Attachment Configuration</div>
              <div className="grid mb-3">
                <div className="col-12 md:col-4">
                  <div className="flex align-items-center gap-2">
                    <Checkbox
                      checked={form.attachments.include_pdf_ledger}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          attachments: { ...prev.attachments, include_pdf_ledger: e.checked ?? false },
                        }))
                      }
                    />
                    <label className="text-sm">PDF Ledger</label>
                  </div>
                </div>
                <div className="col-12 md:col-4">
                  <div className="flex align-items-center gap-2">
                    <Checkbox
                      checked={form.attachments.include_excel_statement}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          attachments: { ...prev.attachments, include_excel_statement: e.checked ?? false },
                        }))
                      }
                    />
                    <label className="text-sm">Excel Statement</label>
                  </div>
                </div>
                <div className="col-12 md:col-4">
                  <div className="flex align-items-center gap-2">
                    <Checkbox
                      checked={form.attachments.include_custom_attachments}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          attachments: { ...prev.attachments, include_custom_attachments: e.checked ?? false },
                        }))
                      }
                    />
                    <label className="text-sm">Custom Attachments</label>
                  </div>
                </div>
                {form.attachments.include_custom_attachments && (
                  <div className="col-12 mt-2">
                    <label className="block mb-2 font-medium text-sm">Custom Attachment Note</label>
                    <InputText
                      value={form.attachments.custom_attachment_note}
                      onChange={(e) =>
                        setForm((prev) => ({
                          ...prev,
                          attachments: { ...prev.attachments, custom_attachment_note: e.target.value },
                        }))
                      }
                      placeholder="Describe custom attachments..."
                      className="w-full"
                    />
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex justify-content-end gap-3 mt-4">
                <Button label="Cancel" className="p-button-outlined" onClick={handleCancel} disabled={saving} />
                <Button label={editingId ? 'Update Template' : 'Save Template'} icon="pi pi-save" onClick={handleSave} loading={saving} />
              </div>
            </div>
          </div>

          {/* Placeholder Reference Panel */}
          <div className="col-12 lg:col-4">
            <div className="em-form-section" style={{ position: 'sticky', top: 24 }}>
              <div className="em-form-section-title">Available Placeholders</div>
              <p className="text-sm mb-3" style={{ color: 'var(--color-text-muted)' }}>
                Click a placeholder to insert it at the cursor position in the subject or body field.
              </p>
              <div className="flex flex-column gap-2">
                {AVAILABLE_PLACEHOLDERS.map((p) => (
                  <div
                    key={p}
                    className="flex align-items-center justify-content-between p-2"
                    style={{
                      background: 'var(--color-surface-50, #f8f9fa)',
                      borderRadius: 'var(--radius-sm, 4px)',
                      cursor: 'pointer',
                    }}
                    onClick={() => insertPlaceholder(p)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => { if (e.key === 'Enter') insertPlaceholder(p); }}
                    aria-label={`Insert placeholder ${p}`}
                  >
                    <code style={{ fontSize: '0.8rem' }}>{`{{${p}}}`}</code>
                    <i className="pi pi-plus-circle" style={{ fontSize: '0.8rem', color: 'var(--color-primary)' }} />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
