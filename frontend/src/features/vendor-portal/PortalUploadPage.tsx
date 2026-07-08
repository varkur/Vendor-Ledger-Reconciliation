/**
 * Vendor Portal Upload page — Allows vendors to upload their statement files.
 * Includes file upload with progress indicator connected to backend API.
 *
 * Connects to: POST /api/v1/vlr/portal/upload (with X-Portal-Token header)
 * Requirements: 24.2
 */

import { useState, useRef } from 'react';
import { FileUpload, FileUploadHandlerEvent } from 'primereact/fileupload';
import { DataTable } from 'primereact/datatable';
import { Column } from 'primereact/column';
import { Tag } from 'primereact/tag';
import { Toast } from 'primereact/toast';
import { ProgressBar } from 'primereact/progressbar';
import { Message } from 'primereact/message';
import { Button } from 'primereact/button';
import { useNavigate } from 'react-router-dom';

import { usePortalUpload } from './hooks/usePortal';
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

export const PortalUploadPage = () => {
  const toast = useRef<Toast>(null);
  const navigate = useNavigate();
  const { portalToken, caseInfo, isAuthenticated } = usePortalContext();
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);

  const { mutateAsync: uploadFile, uploadProgress, isPending } = usePortalUpload(
    portalToken || ''
  );

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
