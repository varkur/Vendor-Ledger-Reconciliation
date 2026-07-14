/**
 * Vendor Portal Upload page — Allows vendors to upload their statement files.
 * Includes file upload with progress indicator connected to backend API.
 * After upload, polls for reconciliation status and auto-navigates on completion.
 *
 * Connects to: POST /api/v1/vlr/portal/upload (with X-Portal-Token header)
 *              GET /api/v1/vlr/portal/reconciliation-status/{case_id} (polling)
 * Requirements: 6, 24.2
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { FileUpload, FileUploadHandlerEvent } from 'primereact/fileupload';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { ProgressBar } from 'primereact/progressbar';
import { ProgressSpinner } from 'primereact/progressspinner';
import { Message } from 'primereact/message';
import { Button } from 'primereact/button';
import { useNavigate } from 'react-router-dom';

import { usePortalUpload, useReconciliationStatus } from './hooks/usePortal';
import { usePortalContext } from './context/PortalContext';

interface UploadedFile {
  id: string;
  fileName: string;
  fileSize: string;
  uploadDate: string;
  status: 'Uploading' | 'Processing' | 'Processed' | 'Error';
  entriesParsed?: number;
  errorMessage?: string;
}

/** Polling timeout duration: 2 minutes */
const POLLING_TIMEOUT_MS = 2 * 60 * 1000;

export const PortalUploadPage = () => {
  const toast = useRef<Toast>(null);
  const navigate = useNavigate();
  const { portalToken, caseInfo, isAuthenticated } = usePortalContext();
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [isPolling, setIsPolling] = useState(false);
  const [pollingTimedOut, setPollingTimedOut] = useState(false);
  const [processingError, setProcessingError] = useState<string | null>(null);
  const pollingStartTime = useRef<number | null>(null);

  const { mutateAsync: uploadFile, uploadProgress, isPending } = usePortalUpload(
    portalToken || ''
  );

  const caseId = caseInfo?.case_id ? String(caseInfo.case_id) : null;

  // Poll for reconciliation status after upload
  const { data: statusData } = useReconciliationStatus(
    caseId,
    portalToken,
    isPolling && !pollingTimedOut
  );

  // Handle polling timeout (2 minutes)
  useEffect(() => {
    if (!isPolling || pollingTimedOut) return;

    const checkTimeout = setInterval(() => {
      if (pollingStartTime.current) {
        const elapsed = Date.now() - pollingStartTime.current;
        if (elapsed >= POLLING_TIMEOUT_MS) {
          setPollingTimedOut(true);
          clearInterval(checkTimeout);
        }
      }
    }, 1000);

    return () => clearInterval(checkTimeout);
  }, [isPolling, pollingTimedOut]);

  // Handle status changes from polling
  useEffect(() => {
    if (!statusData || !isPolling) return;

    if (statusData.status === 'completed') {
      setIsPolling(false);
      toast.current?.show({
        severity: 'success',
        summary: 'Reconciliation Complete',
        detail: 'Your statement has been processed successfully.',
        life: 3000,
      });
      // Auto-navigate to statement page
      setTimeout(() => {
        navigate('/portal/statement');
      }, 1500);
    } else if (statusData.status === 'error') {
      setIsPolling(false);
      setProcessingError(
        statusData.message || 'An error occurred during processing. Please contact support.'
      );
    }
  }, [statusData, isPolling, navigate]);

  // Start polling after a successful upload that returns a task_id
  const startPolling = useCallback(() => {
    setIsPolling(true);
    setPollingTimedOut(false);
    setProcessingError(null);
    pollingStartTime.current = Date.now();
  }, []);

  // Redirect to auth if not authenticated
  if (!isAuthenticated || !portalToken) {
    return (
      <div style={{ maxWidth: 600, margin: '0 auto', padding: '60px 24px', textAlign: 'center' }}>
        <div className="em-card" style={{ padding: 40 }}>
          <i
            className="pi pi-lock"
            style={{ fontSize: '3rem', color: 'var(--color-warning, #f59e0b)' }}
          />
          <h3 style={{ marginTop: 16 }}>Authentication Required</h3>
          <p style={{ color: 'var(--color-text-muted)' }}>
            Please use the link from your email to access the portal.
          </p>
        </div>
      </div>
    );
  }

  const handleUpload = async (event: FileUploadHandlerEvent) => {
    const files = event.files;

    for (const file of files) {
      const fileId = `upload-${Date.now()}-${Math.random().toString(36).slice(2)}`;

      // Add file to list as uploading
      setUploadedFiles((prev) => [
        ...prev,
        {
          id: fileId,
          fileName: file.name,
          fileSize: `${(file.size / 1024).toFixed(0)} KB`,
          uploadDate: new Date().toLocaleString('en-IN', {
            day: '2-digit',
            month: 'short',
            year: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
          }),
          status: 'Uploading',
        },
      ]);

      try {
        const result = await uploadFile(file);

        // Update file status to Processed
        setUploadedFiles((prev) =>
          prev.map((f) =>
            f.id === fileId
              ? {
                  ...f,
                  status: 'Processed' as const,
                  entriesParsed: result.entries_parsed,
                }
              : f
          )
        );

        toast.current?.show({
          severity: 'success',
          summary: 'Upload Complete',
          detail: `${file.name} uploaded successfully. ${result.entries_parsed} entries parsed.`,
          life: 5000,
        });

        // If task_id is returned, start polling for reconciliation status
        if (result.task_id) {
          startPolling();
        }
      } catch (error: unknown) {
        const errorMsg =
          (error as { response?: { data?: { detail?: string } } })?.response?.data
            ?.detail || 'Upload failed. Please try again.';

        // Update file status to Error
        setUploadedFiles((prev) =>
          prev.map((f) =>
            f.id === fileId
              ? { ...f, status: 'Error' as const, errorMessage: errorMsg }
              : f
          )
        );

        toast.current?.show({
          severity: 'error',
          summary: 'Upload Failed',
          detail: errorMsg,
          life: 8000,
        });
      }
    }
  };

  const statusTemplate = (rowData: UploadedFile) => {
    const severityMap: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
      Processed: 'success',
      Processing: 'warning',
      Uploading: 'info',
      Error: 'danger',
    };
    return <Tag value={rowData.status} severity={severityMap[rowData.status]} />;
  };

  const entriesTemplate = (rowData: UploadedFile) => {
    if (rowData.entriesParsed !== undefined) {
      return <span>{rowData.entriesParsed} entries</span>;
    }
    if (rowData.status === 'Error') {
      return (
        <span style={{ color: 'var(--color-error)', fontSize: '0.85rem' }}>
          {rowData.errorMessage || 'Failed'}
        </span>
      );
    }
    return <span style={{ color: 'var(--color-text-muted)' }}>—</span>;
  };

  // Processing state UI — shown while polling
  if (isPolling && !pollingTimedOut && !processingError) {
    return (
      <div style={{ maxWidth: 600, margin: '0 auto', padding: '60px 24px', textAlign: 'center' }}>
        <Toast ref={toast} />
        <div className="em-card" style={{ padding: 48 }}>
          <ProgressSpinner
            style={{ width: '60px', height: '60px' }}
            strokeWidth="4"
            animationDuration="1.5s"
          />
          <h3 style={{ marginTop: 24, marginBottom: 8 }}>Processing your statement...</h3>
          <p style={{ color: 'var(--color-text-muted)', margin: '0 0 24px' }}>
            Your file has been uploaded and reconciliation is in progress.
          </p>
          <div style={{ display: 'flex', justifyContent: 'center', gap: 16, marginBottom: 24 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <i className="pi pi-check-circle" style={{ color: 'var(--color-success, #22c55e)' }} />
              <span style={{ fontSize: '0.85rem' }}>File uploaded</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <ProgressSpinner style={{ width: '16px', height: '16px' }} strokeWidth="5" />
              <span style={{ fontSize: '0.85rem' }}>Reconciling entries</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <i className="pi pi-circle" style={{ color: 'var(--color-text-muted)' }} />
              <span style={{ fontSize: '0.85rem', color: 'var(--color-text-muted)' }}>Complete</span>
            </div>
          </div>
          <p style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
            This usually takes a few minutes. Please do not close this page.
          </p>
        </div>
      </div>
    );
  }

  // Polling timeout state — "Taking longer than expected"
  if (pollingTimedOut && isPolling) {
    return (
      <div style={{ maxWidth: 600, margin: '0 auto', padding: '60px 24px', textAlign: 'center' }}>
        <Toast ref={toast} />
        <div className="em-card" style={{ padding: 48 }}>
          <i className="pi pi-clock" style={{ fontSize: '3rem', color: 'var(--color-warning, #f59e0b)' }} />
          <h3 style={{ marginTop: 16, marginBottom: 8 }}>Taking longer than expected</h3>
          <p style={{ color: 'var(--color-text-muted)', margin: '0 0 24px' }}>
            Your statement is still being processed. This may take a bit more time.
            You can check back later or wait here.
          </p>
          <div className="flex justify-content-center gap-3">
            <Button
              label="Check Back Later"
              icon="pi pi-arrow-left"
              severity="secondary"
              outlined
              onClick={() => { setIsPolling(false); setPollingTimedOut(false); }}
            />
            <Button
              label="Keep Waiting"
              icon="pi pi-refresh"
              onClick={() => { setPollingTimedOut(false); pollingStartTime.current = Date.now(); }}
            />
          </div>
        </div>
      </div>
    );
  }

  // Processing error state
  if (processingError) {
    return (
      <div style={{ maxWidth: 600, margin: '0 auto', padding: '60px 24px', textAlign: 'center' }}>
        <Toast ref={toast} />
        <div className="em-card" style={{ padding: 48 }}>
          <i className="pi pi-exclamation-triangle" style={{ fontSize: '3rem', color: 'var(--color-error, #ef4444)' }} />
          <h3 style={{ marginTop: 16, marginBottom: 8 }}>Processing Error</h3>
          <p style={{ color: 'var(--color-text-muted)', margin: '0 0 16px' }}>{processingError}</p>
          <Message
            severity="info"
            text="Please contact the reconciliation team for assistance. Email: support@company.com"
            className="mb-3 w-full"
          />
          <Button
            label="Try Again"
            icon="pi pi-refresh"
            severity="secondary"
            onClick={() => { setProcessingError(null); }}
          />
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '24px' }}>
      <Toast ref={toast} />

      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: 0 }}>Upload Statement</h2>
        <p style={{ color: 'var(--color-text-muted)', margin: '4px 0 0' }}>
          Upload your ledger statement for reconciliation. Supported formats: Excel
          (.xlsx, .xls), CSV.
        </p>
        {caseInfo && (
          <p style={{ color: 'var(--color-text-muted)', margin: '4px 0 0', fontSize: '0.85rem' }}>
            Vendor: <strong>{caseInfo.vendor_name}</strong> | Uploads:{' '}
            {caseInfo.upload_count}/{caseInfo.max_uploads}
          </p>
        )}
      </div>

      {/* Upload Progress */}
      {isPending && uploadProgress > 0 && (
        <div className="em-card mb-3">
          <div className="flex align-items-center gap-2 mb-2">
            <i className="pi pi-cloud-upload" />
            <span>Uploading file...</span>
          </div>
          <ProgressBar value={uploadProgress} />
        </div>
      )}

      {/* Upload Counter */}
      <div className="em-card mb-3">
        <div className="flex align-items-center justify-content-between">
          <div>
            <span style={{ fontSize: '1.25rem', fontWeight: 600 }}>
              {uploadedFiles.filter((f) => f.status === 'Processed').length}
            </span>
            <span style={{ color: 'var(--color-text-muted)', marginLeft: 8 }}>
              file(s) uploaded successfully
            </span>
          </div>
          <div className="flex gap-2">
            <Tag
              value={`${uploadedFiles.filter((f) => f.status === 'Processed').length} Processed`}
              severity="success"
            />
            {uploadedFiles.filter((f) => f.status === 'Error').length > 0 && (
              <Tag
                value={`${uploadedFiles.filter((f) => f.status === 'Error').length} Failed`}
                severity="danger"
              />
            )}
          </div>
        </div>
      </div>

      {/* Max uploads warning */}
      {caseInfo && caseInfo.upload_count >= caseInfo.max_uploads && (
        <Message
          severity="warn"
          text="Maximum upload limit reached. Please contact the reconciliation team if you need to upload additional files."
          className="mb-3 w-full"
        />
      )}

      {/* File Upload */}
      <div className="em-card mb-3">
        <FileUpload
          name="vendorStatement"
          customUpload
          uploadHandler={handleUpload}
          multiple
          accept=".xlsx,.xls,.csv"
          maxFileSize={10000000}
          disabled={
            isPending ||
            (caseInfo ? caseInfo.upload_count >= caseInfo.max_uploads : false)
          }
          emptyTemplate={
            <div className="flex flex-column align-items-center p-4">
              <i
                className="pi pi-cloud-upload"
                style={{ fontSize: '3rem', color: 'var(--color-text-muted)' }}
              />
              <p style={{ color: 'var(--color-text-muted)', margin: '12px 0 0' }}>
                Drag and drop files here, or click to browse
              </p>
              <p style={{ fontSize: '0.8rem', color: 'var(--color-text-muted)' }}>
                Max file size: 10MB | Supported: .xlsx, .xls, .csv
              </p>
            </div>
          }
          chooseLabel="Browse Files"
          uploadLabel="Upload"
          cancelLabel="Clear"
        />
      </div>

      {/* Uploaded Files Table */}
      {uploadedFiles.length > 0 && (
        <div className="em-card" style={{ padding: 0 }}>
          <div
            style={{
              padding: '12px 16px',
              borderBottom: '1px solid var(--color-border, #e5e7eb)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <h3 style={{ margin: 0, fontSize: '1rem' }}>Uploaded Files</h3>
            {uploadedFiles.some((f) => f.status === 'Processed') && (
              <Button
                label="View Statement"
                icon="pi pi-eye"
                size="small"
                className="p-button-outlined"
                onClick={() => navigate('/portal/statement')}
              />
            )}
          </div>
          <DataTable value={uploadedFiles} emptyMessage="No files uploaded.">
            <Column field="fileName" header="File Name" style={{ width: '35%' }} />
            <Column field="fileSize" header="Size" style={{ width: '10%' }} />
            <Column field="uploadDate" header="Upload Date" style={{ width: '22%' }} />
            <Column
              header="Result"
              body={entriesTemplate}
              style={{ width: '18%' }}
            />
            <Column header="Status" body={statusTemplate} style={{ width: '12%' }} />
          </DataTable>
        </div>
      )}
    </div>
  );
};
