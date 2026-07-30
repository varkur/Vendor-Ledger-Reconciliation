/**
 * Column Mapping / Case Detail Page — Simplified.
 * Shows case info, ledger file status, and a "Start Reconciliation" button.
 * 
 * Since the file parser already extracts document_number, amount, and date,
 * the user just needs to confirm the data looks right and click "Start Reconciliation".
 * 
 * The engine matches primarily on amount + date proximity (since company SAP doc numbers
 * and vendor invoice numbers are typically different formats).
 */

import { useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from 'primereact/button';
import { Toast } from 'primereact/toast';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@shared/services/apiClient';
import { useSelectedEntity } from '@shared/hooks/useSelectedEntity';
import { downloadBlob, filenameFromDisposition } from '@shared/utils/downloadBlob';

interface CaseDetail {
  id: string;
  request_id: string;
  vendor_id: string;
  status: string;
  upload_count: number;
  match_statistics: Record<string, any> | null;
}

interface LedgerEntry {
  document_number: string;
  document_type: string;
  posting_date: string;
  amount: number;
  reference_number: string;
  description: string;
}

export const ColumnMappingPage = () => {
  const { requestId, caseId } = useParams<{ requestId: string; caseId: string }>();
  const navigate = useNavigate();
  const toast = useRef<Toast>(null);
  const queryClient = useQueryClient();
  const { companyCode } = useSelectedEntity();
  const [isReconciling, setIsReconciling] = useState(false);
  const [isSendingReview, setIsSendingReview] = useState(false);
  const [showCompany, setShowCompany] = useState(false);
  const [showVendor, setShowVendor] = useState(false);
  const [busySide, setBusySide] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const companyFileRef = useRef<HTMLInputElement>(null);
  const vendorFileRef = useRef<HTMLInputElement>(null);

  // Fetch case detail
  const { data: caseData, isLoading } = useQuery<CaseDetail>({
    queryKey: ['case-detail', caseId],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/cases/${caseId}`, {
        params: { company_code: companyCode },
      });
      return data;
    },
    enabled: !!caseId && !!companyCode,
  });

  // Fetch vendor info
  const { data: vendorData } = useQuery({
    queryKey: ['vendor-info', caseData?.vendor_id],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/vendors/${caseData!.vendor_id}`, {
        params: { company_code: companyCode },
      });
      return data;
    },
    enabled: !!caseData?.vendor_id && !!companyCode,
  });

  // Per-side presence check — the headers endpoint 404s when a side has no
  // ledger entries, so we use it to know whether each ledger is present.
  const { data: companyHasData } = useQuery<boolean>({
    queryKey: ['ledger-present', caseId, 'company'],
    queryFn: async () => {
      try {
        await apiClient.get(`/vlr/column-mapping/${caseId}/headers`, {
          params: { side: 'company', company_code: companyCode },
        });
        return true;
      } catch (e: any) {
        if (e.response?.status === 404) return false;
        throw e;
      }
    },
    enabled: !!caseId && !!companyCode,
  });

  const { data: vendorHasData } = useQuery<boolean>({
    queryKey: ['ledger-present', caseId, 'vendor'],
    queryFn: async () => {
      try {
        await apiClient.get(`/vlr/column-mapping/${caseId}/headers`, {
          params: { side: 'vendor', company_code: companyCode },
        });
        return true;
      } catch (e: any) {
        if (e.response?.status === 404) return false;
        throw e;
      }
    },
    enabled: !!caseId && !!companyCode,
  });

  // Fetch company entries (sample)
  const { data: companyEntries } = useQuery<LedgerEntry[]>({
    queryKey: ['ledger-entries', caseId, 'company'],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/column-mapping/${caseId}/headers`, {
        params: { side: 'company', company_code: companyCode },
      });
      return data.sample_values ? Object.keys(data.sample_values).map((h, i) => ({
        document_number: data.sample_values['Document Number']?.[i] || '',
        document_type: data.sample_values['Document Type']?.[i] || '',
        posting_date: data.sample_values['Posting Date']?.[i] || '',
        amount: parseFloat(data.sample_values['Amount']?.[i] || '0'),
        reference_number: data.sample_values['Reference Number']?.[i] || '',
        description: data.sample_values['Description/Narration']?.[i] || '',
      })).filter(e => e.document_number) : [];
    },
    enabled: showCompany && !!caseId && !!companyCode,
  });

  // Fetch vendor entries (sample)
  const { data: vendorEntries } = useQuery<LedgerEntry[]>({
    queryKey: ['ledger-entries', caseId, 'vendor'],
    queryFn: async () => {
      const { data } = await apiClient.get(`/vlr/column-mapping/${caseId}/headers`, {
        params: { side: 'vendor', company_code: companyCode },
      });
      return data.sample_values ? Object.keys(data.sample_values).map((h, i) => ({
        document_number: data.sample_values['Document Number']?.[i] || '',
        document_type: data.sample_values['Document Type']?.[i] || '',
        posting_date: data.sample_values['Posting Date']?.[i] || '',
        amount: parseFloat(data.sample_values['Amount']?.[i] || '0'),
        reference_number: data.sample_values['Reference Number']?.[i] || '',
        description: data.sample_values['Description/Narration']?.[i] || '',
      })).filter(e => e.document_number) : [];
    },
    enabled: showVendor && !!caseId && !!companyCode,
  });

  const handleStartReconciliation = async () => {
    if (!caseId) return;
    setIsReconciling(true);
    try {
      const { data } = await apiClient.post(
        `/vlr/cases/${caseId}/start-reconciliation`,
        null,
        { params: { company_code: companyCode } }
      );
      toast.current?.show({
        severity: 'success',
        summary: 'Reconciliation Complete',
        detail: data.message,
        life: 5000,
      });
      queryClient.invalidateQueries({ queryKey: ['case-detail', caseId] });
    } catch (error: any) {
      const detail = error.response?.data?.detail || 'Failed to start reconciliation.';
      toast.current?.show({
        severity: 'error',
        summary: 'Reconciliation Failed',
        detail,
        life: 8000,
      });
    } finally {
      setIsReconciling(false);
    }
  };

  // ─── Export the formatted reconciliation workbook (available post-mapping) ──
  const handleExport = async () => {
    if (!caseId) return;
    setIsExporting(true);
    try {
      const response = await apiClient.get(`/vlr/reconciliation/${caseId}/export`, {
        responseType: 'blob',
      });
      const filename = filenameFromDisposition(
        response.headers['content-disposition'],
        `Reconciliation-${caseId}.xlsx`,
      );
      downloadBlob(
        response.data,
        filename,
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      );
    } catch (error: any) {
      toast.current?.show({
        severity: 'error',
        summary: 'Export Failed',
        detail: error.response?.data?.detail || 'Could not generate the Excel file.',
        life: 6000,
      });
    } finally {
      setIsExporting(false);
    }
  };

  // ─── Ledger file management (download / delete / re-upload) ───────────────
  const handleDownloadLedger = async (side: 'company' | 'vendor') => {
    if (!caseId) return;
    try {
      const response = await apiClient.get(`/vlr/column-mapping/${caseId}/download`, {
        params: { side, company_code: companyCode },
        responseType: 'blob',
      });
      // Filename: partycode_partyname_ledger.csv (sanitized for filesystem)
      const partyCode = (vendorData as any)?.vendor_code || 'party';
      const partyName = (vendorData as any)?.name || side;
      const sanitize = (s: string) => s.replace(/[^a-zA-Z0-9]+/g, '_').replace(/^_+|_+$/g, '');
      downloadBlob(
        response.data,
        `${sanitize(partyCode)}_${sanitize(partyName)}_ledger.csv`,
        'text/csv',
      );
    } catch (error: any) {
      const detail = error.response?.status === 404
        ? `No ${side} ledger data to download.`
        : error.response?.data?.detail || 'Download failed.';
      toast.current?.show({ severity: 'warn', summary: 'Download', detail, life: 5000 });
    }
  };

  const handleDeleteLedger = async (side: 'company' | 'vendor') => {
    if (!caseId) return;
    if (!window.confirm(`Delete the ${side} ledger? You'll need to re-upload it before reconciling again.`)) {
      return;
    }
    setBusySide(`delete-${side}`);
    try {
      const { data } = await apiClient.delete(`/vlr/column-mapping/${caseId}/ledger`, {
        params: { side, company_code: companyCode },
      });
      toast.current?.show({ severity: 'success', summary: 'Deleted', detail: data.message, life: 4000 });
      if (side === 'company') setShowCompany(false); else setShowVendor(false);
      queryClient.invalidateQueries({ queryKey: ['case-detail', caseId] });
      queryClient.invalidateQueries({ queryKey: ['ledger-entries', caseId, side] });
      queryClient.invalidateQueries({ queryKey: ['ledger-present', caseId, side] });
    } catch (error: any) {
      const detail = error.response?.data?.detail || 'Delete failed.';
      toast.current?.show({ severity: 'error', summary: 'Delete Failed', detail, life: 6000 });
    } finally {
      setBusySide(null);
    }
  };

  const handleReuploadLedger = async (side: 'company' | 'vendor', file: File) => {
    if (!caseId || !file) return;
    setBusySide(`upload-${side}`);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const { data } = await apiClient.post(
        `/vlr/column-mapping/${caseId}/reupload`,
        formData,
        {
          params: { side, company_code: companyCode },
          headers: { 'Content-Type': 'multipart/form-data' },
        }
      );
      toast.current?.show({ severity: 'success', summary: 'Uploaded', detail: data.message, life: 4000 });
      queryClient.invalidateQueries({ queryKey: ['case-detail', caseId] });
      queryClient.invalidateQueries({ queryKey: ['ledger-entries', caseId, side] });
      queryClient.invalidateQueries({ queryKey: ['ledger-present', caseId, side] });
    } catch (error: any) {
      const detail = error.response?.data?.detail || 'Upload failed.';
      toast.current?.show({ severity: 'error', summary: 'Upload Failed', detail, life: 8000 });
    } finally {
      setBusySide(null);
    }
  };

  if (isLoading) {
    return (
      <div className="flex justify-content-center align-items-center" style={{ minHeight: 300 }}>
        <ProgressSpinner style={{ width: '50px', height: '50px' }} />
      </div>
    );
  }

  const status = caseData?.status || '';
  // Reconciliation can run once the vendor ledger is uploaded. Manual column
  // mapping is optional since the parser already extracts amount/date/doc number,
  // so allow it from mapping_pending as well as statement_mapped / in_progress.
  // Both ledgers must be present to reconcile. companyHasData/vendorHasData are
  // undefined while loading — treat undefined as "present" so we don't flash
  // the disabled state on first load.
  const bothLedgersPresent = companyHasData !== false && vendorHasData !== false;
  const canStartReco =
    bothLedgersPresent &&
    (status === 'statement_mapped' ||
      status === 'mapping_pending' ||
      status === 'in_progress');
  const canSendForReview = status === 'statement_mapped' || status === 'auto_completed';

  const handleSendForReview = async () => {
    if (!caseId) return;
    setIsSendingReview(true);
    try {
      await apiClient.post('/vlr/cases/bulk-review', {
        company_code: companyCode,
        case_ids: [caseId],
      });
      toast.current?.show({
        severity: 'success',
        summary: 'Sent for Review',
        detail: 'Case has been sent for review.',
        life: 4000,
      });
      queryClient.invalidateQueries({ queryKey: ['case-detail', caseId] });
      setTimeout(() => navigate(`/track-reconciliation/${requestId}?tab=reviewStage`), 1200);
    } catch (error: any) {
      const detail = error.response?.data?.detail || 'Failed to send for review.';
      toast.current?.show({ severity: 'error', summary: 'Failed', detail, life: 6000 });
    } finally {
      setIsSendingReview(false);
    }
  };

  return (
    <div>
      <Toast ref={toast} />

      {/* Back */}
      <Button
        label="Back to Cases"
        icon="pi pi-arrow-left"
        className="p-button-text p-button-sm mb-3"
        onClick={() => navigate(`/track-reconciliation/${requestId}`)}
      />

      {/* Case Info */}
      <div className="em-card mb-4" style={{ padding: '20px' }}>
        <div className="grid">
          <div className="col-6 md:col-3">
            <div className="text-sm" style={{ color: 'var(--color-text-muted)' }}>Party Code</div>
            <div className="font-bold">{(vendorData as any)?.vendor_code || '—'}</div>
          </div>
          <div className="col-6 md:col-3">
            <div className="text-sm" style={{ color: 'var(--color-text-muted)' }}>Party Name</div>
            <div className="font-bold">{(vendorData as any)?.name || '—'}</div>
          </div>
          <div className="col-6 md:col-3">
            <div className="text-sm" style={{ color: 'var(--color-text-muted)' }}>Status</div>
            <div className="font-bold" style={{ color: status === 'auto_completed' ? '#10b981' : '#f59e0b' }}>
              {status.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
            </div>
          </div>
          <div className="col-6 md:col-3">
            <div className="text-sm" style={{ color: 'var(--color-text-muted)' }}>Upload Count</div>
            <div className="font-bold">{caseData?.upload_count || 0}</div>
          </div>
        </div>
      </div>

      {/* Ledger Cards */}
      <div className="grid mb-4">
        <div className="col-12 md:col-6">
          <div
            className="em-card"
            style={{
              padding: '20px',
              borderLeft: '4px solid #10b981',
              opacity: companyHasData === false ? 0.75 : 1,
              background: companyHasData === false ? 'var(--color-surface-alt, #f8f9fa)' : undefined,
            }}
          >
            <div className="flex align-items-center justify-content-between mb-2">
              <h4 className="m-0">Company Ledger</h4>
              {companyHasData !== false && (
                <div className="flex gap-2">
                  <Button
                    label="Map"
                    icon="pi pi-cog"
                    className="p-button-text p-button-sm"
                    onClick={() => navigate(`/track-reconciliation/${requestId}/${caseId}/mapping/company`)}
                  />
                  <Button
                    label={showCompany ? 'Hide' : 'Preview'}
                    icon={showCompany ? 'pi pi-eye-slash' : 'pi pi-eye'}
                    className="p-button-text p-button-sm"
                    onClick={() => setShowCompany(!showCompany)}
                  />
                </div>
              )}
            </div>

            {/* Hidden file input (shared by empty-state and re-upload button) */}
            <input
              type="file"
              ref={companyFileRef}
              style={{ display: 'none' }}
              accept=".csv,.xlsx,.xls"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleReuploadLedger('company', f);
                e.target.value = '';
              }}
            />

            {companyHasData === false ? (
              /* Empty state — only Upload is available */
              <div style={{ textAlign: 'center', padding: '16px 0' }}>
                <i className="pi pi-inbox" style={{ fontSize: '1.75rem', color: 'var(--color-text-muted)' }} />
                <div className="my-2" style={{ color: 'var(--color-text-muted)' }}>
                  No company ledger uploaded. Upload a file to continue.
                </div>
                <Button
                  label="Upload Company Ledger"
                  icon={busySide === 'upload-company' ? 'pi pi-spin pi-spinner' : 'pi pi-upload'}
                  className="p-button-sm"
                  style={{ background: '#10b981', border: 'none' }}
                  disabled={busySide !== null}
                  onClick={() => companyFileRef.current?.click()}
                />
              </div>
            ) : (
              <>
                {/* File actions: right-aligned */}
                <div className="flex gap-2 mb-2 justify-content-end">
                  <Button
                    label="Download"
                    icon="pi pi-download"
                    className="p-button-outlined p-button-sm"
                    onClick={() => handleDownloadLedger('company')}
                  />
                  <Button
                    label="Re-upload"
                    icon={busySide === 'upload-company' ? 'pi pi-spin pi-spinner' : 'pi pi-upload'}
                    className="p-button-outlined p-button-sm"
                    disabled={busySide !== null}
                    onClick={() => companyFileRef.current?.click()}
                  />
                  <Button
                    label="Delete"
                    icon={busySide === 'delete-company' ? 'pi pi-spin pi-spinner' : 'pi pi-trash'}
                    className="p-button-outlined p-button-danger p-button-sm"
                    disabled={busySide !== null}
                    onClick={() => handleDeleteLedger('company')}
                  />
                </div>
                {showCompany && companyEntries && (
                  <DataTable value={companyEntries} size="small" scrollable scrollHeight="200px">
                    <Column field="document_number" header="Doc No" />
                    <Column field="amount" header="Amount" body={(r) => r.amount?.toLocaleString('en-IN')} />
                    <Column field="posting_date" header="Date" />
                    <Column field="document_type" header="Type" />
                  </DataTable>
                )}
                {showCompany && !companyEntries && <ProgressSpinner style={{ width: 30, height: 30 }} />}
              </>
            )}
          </div>
        </div>

        <div className="col-12 md:col-6">
          <div
            className="em-card"
            style={{
              padding: '20px',
              borderLeft: '4px solid #f59e0b',
              opacity: vendorHasData === false ? 0.75 : 1,
              background: vendorHasData === false ? 'var(--color-surface-alt, #f8f9fa)' : undefined,
            }}
          >
            <div className="flex align-items-center justify-content-between mb-2">
              <h4 className="m-0">Vendor Ledger</h4>
              {vendorHasData !== false && (
                <div className="flex gap-2">
                  <Button
                    label="Map"
                    icon="pi pi-cog"
                    className="p-button-text p-button-sm"
                    onClick={() => navigate(`/track-reconciliation/${requestId}/${caseId}/mapping/vendor`)}
                  />
                  <Button
                    label={showVendor ? 'Hide' : 'Preview'}
                    icon={showVendor ? 'pi pi-eye-slash' : 'pi pi-eye'}
                    className="p-button-text p-button-sm"
                    onClick={() => setShowVendor(!showVendor)}
                  />
                </div>
              )}
            </div>

            {/* Hidden file input (shared by empty-state and re-upload button) */}
            <input
              type="file"
              ref={vendorFileRef}
              style={{ display: 'none' }}
              accept=".csv,.xlsx,.xls"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleReuploadLedger('vendor', f);
                e.target.value = '';
              }}
            />

            {vendorHasData === false ? (
              /* Empty state — only Upload is available */
              <div style={{ textAlign: 'center', padding: '16px 0' }}>
                <i className="pi pi-inbox" style={{ fontSize: '1.75rem', color: 'var(--color-text-muted)' }} />
                <div className="my-2" style={{ color: 'var(--color-text-muted)' }}>
                  No vendor ledger uploaded. Upload a file to continue.
                </div>
                <Button
                  label="Upload Vendor Ledger"
                  icon={busySide === 'upload-vendor' ? 'pi pi-spin pi-spinner' : 'pi pi-upload'}
                  className="p-button-sm"
                  style={{ background: '#f59e0b', border: 'none' }}
                  disabled={busySide !== null}
                  onClick={() => vendorFileRef.current?.click()}
                />
              </div>
            ) : (
              <>
                {/* File actions: right-aligned */}
                <div className="flex gap-2 mb-2 justify-content-end">
                  <Button
                    label="Download"
                    icon="pi pi-download"
                    className="p-button-outlined p-button-sm"
                    onClick={() => handleDownloadLedger('vendor')}
                  />
                  <Button
                    label="Re-upload"
                    icon={busySide === 'upload-vendor' ? 'pi pi-spin pi-spinner' : 'pi pi-upload'}
                    className="p-button-outlined p-button-sm"
                    disabled={busySide !== null}
                    onClick={() => vendorFileRef.current?.click()}
                  />
                  <Button
                    label="Delete"
                    icon={busySide === 'delete-vendor' ? 'pi pi-spin pi-spinner' : 'pi pi-trash'}
                    className="p-button-outlined p-button-danger p-button-sm"
                    disabled={busySide !== null}
                    onClick={() => handleDeleteLedger('vendor')}
                  />
                </div>
                {showVendor && vendorEntries && (
                  <DataTable value={vendorEntries} size="small" scrollable scrollHeight="200px">
                    <Column field="document_number" header="Doc No" />
                    <Column field="amount" header="Amount" body={(r) => r.amount?.toLocaleString('en-IN')} />
                    <Column field="posting_date" header="Date" />
                    <Column field="document_type" header="Type" />
                  </DataTable>
                )}
                {showVendor && !vendorEntries && <ProgressSpinner style={{ width: 30, height: 30 }} />}
              </>
            )}
          </div>
        </div>
      </div>

      {/* Info message */}
      <Message
        severity="info"
        className="w-full mb-4"
        text="The reconciliation engine matches entries by amount, date proximity, and reference number similarity. Click 'Start Reconciliation' to run the matching algorithm."
      />

      {/* Start Reconciliation + Send for Review + Export */}
      <div className="flex justify-content-center gap-3">
        {status !== 'mapping_pending' && (
          <Button
            label="Download Excel"
            icon={isExporting ? 'pi pi-spin pi-spinner' : 'pi pi-file-excel'}
            className="p-button-lg p-button-success"
            style={{ padding: '14px 32px', fontSize: '1.1rem', color: '#fff' }}
            disabled={isExporting}
            onClick={handleExport}
          />
        )}
        <Button
          label="Start Reconciliation"
          icon={isReconciling ? 'pi pi-spin pi-spinner' : 'pi pi-play'}
          className="p-button-lg"
          style={{ background: '#10b981', border: 'none', padding: '14px 48px', fontSize: '1.1rem' }}
          disabled={!canStartReco || isReconciling}
          loading={isReconciling}
          onClick={handleStartReconciliation}
        />
        {canSendForReview && (
          <Button
            label="Send for Review"
            icon={isSendingReview ? 'pi pi-spin pi-spinner' : 'pi pi-send'}
            className="p-button-lg p-button-outlined"
            style={{ padding: '14px 48px', fontSize: '1.1rem' }}
            disabled={isSendingReview}
            loading={isSendingReview}
            onClick={handleSendForReview}
          />
        )}
      </div>

      {/* Match Statistics */}
      {caseData?.match_statistics && (
        <div className="em-card mt-4" style={{ padding: '20px' }}>
          <h4 className="mt-0">Match Results</h4>
          <div className="grid">
            <div className="col-6 md:col-2">
              <div className="text-center">
                <div className="text-2xl font-bold" style={{ color: '#10b981' }}>
                  {caseData.match_statistics.total_matched_company || 0}
                </div>
                <div className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Matched (Company)</div>
              </div>
            </div>
            <div className="col-6 md:col-2">
              <div className="text-center">
                <div className="text-2xl font-bold" style={{ color: '#10b981' }}>
                  {caseData.match_statistics.total_matched_vendor || 0}
                </div>
                <div className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Matched (Vendor)</div>
              </div>
            </div>
            <div className="col-6 md:col-2">
              <div className="text-center">
                <div className="text-2xl font-bold">{caseData.match_statistics.total_company_entries || 0}</div>
                <div className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Total Company</div>
              </div>
            </div>
            <div className="col-6 md:col-2">
              <div className="text-center">
                <div className="text-2xl font-bold">{caseData.match_statistics.total_vendor_entries || 0}</div>
                <div className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Total Vendor</div>
              </div>
            </div>
            <div className="col-6 md:col-2">
              <div className="text-center">
                <div className="text-2xl font-bold" style={{ color: '#f59e0b' }}>
                  {(caseData.match_statistics.total_company_entries || 0) - (caseData.match_statistics.total_matched_company || 0)}
                </div>
                <div className="text-xs" style={{ color: 'var(--color-text-muted)' }}>Unmatched</div>
              </div>
            </div>
            <div className="col-6 md:col-2">
              <div className="text-center">
                <Button
                  label="View Output"
                  icon="pi pi-external-link"
                  className="p-button-sm p-button-outlined"
                  onClick={() => navigate(`/track-reconciliation/${requestId}/case/${caseId}`)}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Manual Mapping Option */}
      <div className="em-card mt-4" style={{ padding: '16px' }}>
        <div className="flex align-items-center justify-content-between">
          <div>
            <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
              After mapping both ledgers, click "Start Reconciliation" to run the matching engine.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
