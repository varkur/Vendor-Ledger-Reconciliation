/**
 * Reminders Configuration page — manage reminder groups and templates.
 * Views: Group list (paginated, searchable) → Group detail → Reminder preview dialog.
 *
 * Requirements: Reminder management for VLR confirmation workflows.
 */

import { useState, useRef } from 'react';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Button } from 'primereact/button';
import { InputText } from 'primereact/inputtext';
import { InputTextarea } from 'primereact/inputtextarea';
import { InputNumber } from 'primereact/inputnumber';
import { Dialog } from 'primereact/dialog';
import { Toast } from 'primereact/toast';
import { Paginator, type PaginatorPageChangeEvent } from 'primereact/paginator';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@shared/services/apiClient';
import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface ReminderTemplate {
  id: string;
  name: string;
  email_subject: string;
  email_content: string;
}

interface ReminderGroup {
  id: string;
  name: string;
  interval_days: number;
  total_reminders: number;
  creator: string;
  reminders: ReminderTemplate[];
}

interface ReminderGroupListResponse {
  items: ReminderGroup[];
  total: number;
  page: number;
  page_size: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// API
// ─────────────────────────────────────────────────────────────────────────────

async function getGroups(
  companyCode: string,
  page: number,
  pageSize: number,
  search: string
): Promise<ReminderGroupListResponse> {
  const { data } = await apiClient.get<ReminderGroupListResponse>('/vlr/settings/reminders', {
    params: { company_code: companyCode, page, page_size: pageSize, search: search || undefined },
  });
  return data;
}

async function getGroupDetail(companyCode: string, groupId: string): Promise<ReminderGroup> {
  const { data } = await apiClient.get<ReminderGroup>(`/vlr/settings/reminders/${groupId}`, {
    params: { company_code: companyCode },
  });
  return data;
}

async function updateReminderTemplate(
  companyCode: string,
  groupId: string,
  reminderId: string,
  payload: { name?: string; email_subject?: string; email_content?: string }
): Promise<ReminderTemplate> {
  const { data } = await apiClient.put<ReminderTemplate>(
    `/vlr/settings/reminders/${groupId}/reminders/${reminderId}`,
    payload,
    { params: { company_code: companyCode } }
  );
  return data;
}

async function createReminderGroup(
  companyCode: string,
  payload: { name: string; interval_days: number; total_reminders: number }
): Promise<ReminderGroup> {
  const { data } = await apiClient.post<ReminderGroup>('/vlr/reminder-configs', {
    ...payload,
    company_code: companyCode,
  });
  return data;
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export const RemindersPage = () => {
  const { companyCode } = useSelectedEntity();
  const queryClient = useQueryClient();
  const toast = useRef<Toast>(null);

  // View state
  const [view, setView] = useState<'list' | 'detail'>('list');
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);

  // List pagination & search
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');

  // Preview dialog
  const [previewVisible, setPreviewVisible] = useState(false);
  const [previewReminder, setPreviewReminder] = useState<ReminderTemplate | null>(null);

  // Edit dialog
  const [editVisible, setEditVisible] = useState(false);
  const [editReminder, setEditReminder] = useState<ReminderTemplate | null>(null);
  const [editSubject, setEditSubject] = useState('');
  const [editContent, setEditContent] = useState('');
  const [editName, setEditName] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  // Create Group dialog
  const [createGroupVisible, setCreateGroupVisible] = useState(false);
  const [createGroupName, setCreateGroupName] = useState('');
  const [createIntervalDays, setCreateIntervalDays] = useState<number | null>(null);
  const [createTotalReminders, setCreateTotalReminders] = useState<number | null>(3);
  const [isCreatingGroup, setIsCreatingGroup] = useState(false);
  const [createGroupErrors, setCreateGroupErrors] = useState<{ name?: string; interval_days?: string; total_reminders?: string }>({});

  // ─── Queries ─────────────────────────────────────────────────────────────

  const groupsQuery = useQuery<ReminderGroupListResponse, Error>({
    queryKey: ['reminder-groups', companyCode, page, pageSize, search],
    queryFn: () => getGroups(companyCode, page, pageSize, search),
    enabled: !!companyCode && view === 'list',
    retry: 2,
    staleTime: 30_000,
  });

  const detailQuery = useQuery<ReminderGroup, Error>({
    queryKey: ['reminder-group-detail', companyCode, selectedGroupId],
    queryFn: () => getGroupDetail(companyCode, selectedGroupId!),
    enabled: !!companyCode && !!selectedGroupId && view === 'detail',
    retry: 2,
    staleTime: 30_000,
  });

  // ─── Handlers ────────────────────────────────────────────────────────────

  const handleSearch = () => {
    setSearch(searchInput);
    setPage(1);
  };

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  const handleViewGroup = (group: ReminderGroup) => {
    setSelectedGroupId(group.id);
    setView('detail');
  };

  const handleBackToList = () => {
    setView('list');
    setSelectedGroupId(null);
  };

  const handlePreviewReminder = (reminder: ReminderTemplate) => {
    setPreviewReminder(reminder);
    setPreviewVisible(true);
  };

  const handleEditReminder = (reminder: ReminderTemplate) => {
    setEditReminder(reminder);
    setEditName(reminder.name);
    setEditSubject(reminder.email_subject);
    setEditContent(reminder.email_content);
    setEditVisible(true);
  };

  const handleSaveEdit = async () => {
    if (!editReminder || !selectedGroupId) return;
    setIsSaving(true);
    try {
      await updateReminderTemplate(companyCode, selectedGroupId, editReminder.id, {
        name: editName,
        email_subject: editSubject,
        email_content: editContent,
      });
      toast.current?.show({
        severity: 'success',
        summary: 'Template Updated',
        detail: 'Reminder template saved successfully.',
      });
      setEditVisible(false);
      // Refresh detail data
      queryClient.invalidateQueries({ queryKey: ['reminder-group-detail', companyCode, selectedGroupId] });
    } catch (err: any) {
      toast.current?.show({
        severity: 'error',
        summary: 'Save Failed',
        detail: err.response?.data?.detail || 'Failed to update template.',
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handlePageChange = (e: PaginatorPageChangeEvent) => {
    setPage(e.page + 1);
  };

  // ─── Create Group Handlers ───────────────────────────────────────────────

  const handleOpenCreateGroup = () => {
    setCreateGroupName('');
    setCreateIntervalDays(null);
    setCreateTotalReminders(3);
    setCreateGroupErrors({});
    setCreateGroupVisible(true);
  };

  const validateCreateGroup = (): boolean => {
    const errors: { name?: string; interval_days?: string; total_reminders?: string } = {};
    if (!createGroupName.trim()) {
      errors.name = 'Group name is required.';
    }
    if (createIntervalDays === null || createIntervalDays <= 0) {
      errors.interval_days = 'Interval days must be greater than 0.';
    }
    if (createTotalReminders === null || createTotalReminders <= 0) {
      errors.total_reminders = 'Number of reminders must be greater than 0.';
    }
    setCreateGroupErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleCreateGroup = async () => {
    if (!validateCreateGroup()) return;
    setIsCreatingGroup(true);
    setCreateGroupErrors({});
    try {
      await createReminderGroup(companyCode, {
        name: createGroupName.trim(),
        interval_days: createIntervalDays!,
        total_reminders: createTotalReminders!,
      });
      toast.current?.show({
        severity: 'success',
        summary: 'Group Created',
        detail: 'Reminder group created successfully.',
      });
      setCreateGroupVisible(false);
      queryClient.invalidateQueries({ queryKey: ['reminder-groups'] });
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      if (typeof detail === 'string') {
        setCreateGroupErrors({ name: detail });
      } else if (Array.isArray(detail)) {
        // Handle FastAPI validation errors array
        const fieldErrors: { name?: string; interval_days?: string; total_reminders?: string } = {};
        detail.forEach((e: any) => {
          const field = e.loc?.[e.loc.length - 1];
          if (field === 'name') fieldErrors.name = e.msg;
          else if (field === 'interval_days') fieldErrors.interval_days = e.msg;
          else if (field === 'total_reminders') fieldErrors.total_reminders = e.msg;
        });
        setCreateGroupErrors(Object.keys(fieldErrors).length > 0 ? fieldErrors : { name: 'Failed to create group.' });
      } else {
        setCreateGroupErrors({ name: 'Failed to create group. Please try again.' });
      }
    } finally {
      setIsCreatingGroup(false);
    }
  };

  // ─── List View ───────────────────────────────────────────────────────────

  const renderListView = () => {
    if (groupsQuery.isLoading) {
      return (
        <div className="flex justify-content-center align-items-center" style={{ minHeight: 300 }}>
          <ProgressSpinner style={{ width: '50px', height: '50px' }} />
        </div>
      );
    }

    if (groupsQuery.isError) {
      return (
        <div className="flex flex-column align-items-center gap-3" style={{ padding: '2rem' }}>
          <Message severity="error" text={groupsQuery.error?.message || 'Failed to load reminder groups.'} />
          <Button label="Retry" icon="pi pi-refresh" onClick={() => groupsQuery.refetch()} />
        </div>
      );
    }

    const data = groupsQuery.data;

    return (
      <>
        {/* Header */}
        <div className="em-page-header">
          <h2>Reminders</h2>
          <div className="em-page-header-actions">
            <Button label="Create Group" icon="pi pi-plus" onClick={handleOpenCreateGroup} />
          </div>
        </div>

        {/* Search */}
        <div className="flex align-items-center gap-2 mb-3">
          <span className="p-input-icon-left">
            <i className="pi pi-search" />
            <InputText
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={handleSearchKeyDown}
              placeholder="Search groups..."
              style={{ paddingLeft: '2.5rem' }}
            />
          </span>
          <Button label="Search" icon="pi pi-search" onClick={handleSearch} className="p-button-outlined" />
        </div>

        {/* Table */}
        <div className="em-card">
          <DataTable value={data?.items || []} responsiveLayout="scroll" emptyMessage="No reminder groups found.">
            <Column field="name" header="Group Name" />
            <Column field="total_reminders" header="Total Reminders" style={{ width: '150px' }} />
            <Column field="creator" header="Creator" style={{ width: '120px' }} />
            <Column
              header="Action"
              style={{ width: '100px' }}
              body={(rowData: ReminderGroup) => (
                <Button
                  label="View"
                  icon="pi pi-eye"
                  className="p-button-text p-button-sm"
                  onClick={() => handleViewGroup(rowData)}
                />
              )}
            />
          </DataTable>

          {/* Paginator */}
          {data && data.total > pageSize && (
            <Paginator
              first={(page - 1) * pageSize}
              rows={pageSize}
              totalRecords={data.total}
              onPageChange={handlePageChange}
              className="mt-3"
            />
          )}
        </div>
      </>
    );
  };

  // ─── Detail View ─────────────────────────────────────────────────────────

  const renderDetailView = () => {
    if (detailQuery.isLoading) {
      return (
        <div className="flex justify-content-center align-items-center" style={{ minHeight: 300 }}>
          <ProgressSpinner style={{ width: '50px', height: '50px' }} />
        </div>
      );
    }

    if (detailQuery.isError) {
      return (
        <div className="flex flex-column align-items-center gap-3" style={{ padding: '2rem' }}>
          <Message severity="error" text={detailQuery.error?.message || 'Failed to load group detail.'} />
          <Button label="Retry" icon="pi pi-refresh" onClick={() => detailQuery.refetch()} />
        </div>
      );
    }

    const group = detailQuery.data;

    return (
      <>
        {/* Header */}
        <div className="em-page-header">
          <h2>{group?.name || 'Group Detail'}</h2>
          <div className="em-page-header-actions">
            <Button
              label="View Groups"
              icon="pi pi-arrow-left"
              className="p-button-outlined"
              onClick={handleBackToList}
            />
          </div>
        </div>

        {/* Reminders table */}
        <div className="em-card">
          <DataTable
            value={group?.reminders || []}
            responsiveLayout="scroll"
            emptyMessage="No reminders in this group."
          >
            <Column field="id" header="Id" style={{ width: '80px' }} />
            <Column
              header="Group"
              body={() => group?.name || ''}
            />
            <Column field="name" header="Reminder Name" />
            <Column
              header="Number of Reminders"
              body={() => group?.total_reminders || 0}
              style={{ width: '160px' }}
            />
            <Column
              header="Interval"
              body={() => `${group?.interval_days || 0} days`}
              style={{ width: '100px' }}
            />
            <Column
              header="Action"
              style={{ width: '150px' }}
              body={(rowData: ReminderTemplate) => (
                <div className="flex gap-1">
                  <Button
                    label="View"
                    icon="pi pi-eye"
                    className="p-button-text p-button-sm"
                    onClick={() => handlePreviewReminder(rowData)}
                  />
                  <Button
                    label="Edit"
                    icon="pi pi-pencil"
                    className="p-button-text p-button-sm"
                    onClick={() => handleEditReminder(rowData)}
                  />
                </div>
              )}
            />
          </DataTable>
        </div>
      </>
    );
  };

  // ─── Preview Dialog ──────────────────────────────────────────────────────

  const renderPreviewDialog = () => (
    <Dialog
      header="Reminder Preview"
      visible={previewVisible}
      style={{ width: '50vw', maxWidth: '700px' }}
      onHide={() => setPreviewVisible(false)}
      dismissableMask
      modal
    >
      {previewReminder && (
        <div className="flex flex-column gap-3">
          <div>
            <label className="font-bold text-sm block mb-1">Email Subject</label>
            <div className="p-3 surface-ground border-round">{previewReminder.email_subject}</div>
          </div>
          <div>
            <label className="font-bold text-sm block mb-1">Email Content</label>
            <div
              className="p-3 surface-ground border-round"
              style={{ whiteSpace: 'pre-wrap', maxHeight: '400px', overflow: 'auto' }}
            >
              {previewReminder.email_content}
            </div>
          </div>
        </div>
      )}
    </Dialog>
  );

  // ─── Edit Dialog ──────────────────────────────────────────────────────────

  const renderEditDialog = () => (
    <Dialog
      header="Edit Reminder Template"
      visible={editVisible}
      style={{ width: '55vw', maxWidth: '750px' }}
      onHide={() => setEditVisible(false)}
      modal
    >
      {editReminder && (
        <div className="flex flex-column gap-3">
          <div>
            <label htmlFor="edit-name" className="font-bold text-sm block mb-1">
              Template Name
            </label>
            <InputText
              id="edit-name"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              className="w-full"
            />
          </div>
          <div>
            <label htmlFor="edit-subject" className="font-bold text-sm block mb-1">
              Email Subject
            </label>
            <InputText
              id="edit-subject"
              value={editSubject}
              onChange={(e) => setEditSubject(e.target.value)}
              className="w-full"
            />
          </div>
          <div>
            <label htmlFor="edit-content" className="font-bold text-sm block mb-1">
              Email Content
            </label>
            <InputTextarea
              id="edit-content"
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              rows={12}
              className="w-full"
              autoResize
            />
          </div>
          <div className="flex justify-content-end gap-2 pt-2">
            <Button
              label="Cancel"
              className="p-button-text"
              onClick={() => setEditVisible(false)}
            />
            <Button
              label="Save"
              icon="pi pi-save"
              onClick={handleSaveEdit}
              loading={isSaving}
            />
          </div>
        </div>
      )}
    </Dialog>
  );

  // ─── Create Group Dialog ─────────────────────────────────────────────────

  const renderCreateGroupDialog = () => (
    <Dialog
      header="Create Reminder Group"
      visible={createGroupVisible}
      style={{ width: '450px' }}
      onHide={() => setCreateGroupVisible(false)}
      modal
    >
      <div className="flex flex-column gap-3">
        <div>
          <label htmlFor="create-group-name" className="font-bold text-sm block mb-1">
            Group Name *
          </label>
          <InputText
            id="create-group-name"
            value={createGroupName}
            onChange={(e) => setCreateGroupName(e.target.value)}
            className={`w-full ${createGroupErrors.name ? 'p-invalid' : ''}`}
            placeholder="Enter group name"
          />
          {createGroupErrors.name && (
            <small className="p-error block mt-1">{createGroupErrors.name}</small>
          )}
        </div>
        <div>
          <label htmlFor="create-interval-days" className="font-bold text-sm block mb-1">
            Interval Days *
          </label>
          <InputNumber
            id="create-interval-days"
            value={createIntervalDays}
            onValueChange={(e) => setCreateIntervalDays(e.value ?? null)}
            className={`w-full ${createGroupErrors.interval_days ? 'p-invalid' : ''}`}
            placeholder="Days between reminders"
            min={1}
          />
          {createGroupErrors.interval_days && (
            <small className="p-error block mt-1">{createGroupErrors.interval_days}</small>
          )}
        </div>
        <div>
          <label htmlFor="create-total-reminders" className="font-bold text-sm block mb-1">
            Number of Reminders *
          </label>
          <InputNumber
            id="create-total-reminders"
            value={createTotalReminders}
            onValueChange={(e) => setCreateTotalReminders(e.value ?? null)}
            className={`w-full ${createGroupErrors.total_reminders ? 'p-invalid' : ''}`}
            placeholder="Number of reminders"
            min={1}
          />
          {createGroupErrors.total_reminders && (
            <small className="p-error block mt-1">{createGroupErrors.total_reminders}</small>
          )}
        </div>
        <div className="flex justify-content-end gap-2 pt-2">
          <Button
            label="Cancel"
            className="p-button-text"
            onClick={() => setCreateGroupVisible(false)}
            disabled={isCreatingGroup}
          />
          <Button
            label="Create"
            icon="pi pi-plus"
            onClick={handleCreateGroup}
            loading={isCreatingGroup}
          />
        </div>
      </div>
    </Dialog>
  );

  // ─── Render ──────────────────────────────────────────────────────────────

  return (
    <div>
      <Toast ref={toast} />
      {view === 'list' ? renderListView() : renderDetailView()}
      {renderPreviewDialog()}
      {renderEditDialog()}
      {renderCreateGroupDialog()}
    </div>
  );
};
